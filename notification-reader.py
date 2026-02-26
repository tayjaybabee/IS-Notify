from __future__ import annotations

import asyncio
import re
import unicodedata
from dataclasses import dataclass
from typing import Optional, Set, Tuple

from is_matrix_forge.led_matrix.controller import get_controllers
from is_matrix_forge.led_matrix.controller.helpers import find_leftmost, find_rightmost

# -----------------------------
# Matrix setup (IS-Matrix-Forge)
# -----------------------------
CONTROLLERS = get_controllers(threaded=True, skip_all_init_animations=True)
RIGHT = find_rightmost(CONTROLLERS)

LEFT = None
try:
    LEFT = find_leftmost(CONTROLLERS)
except Exception:
    LEFT = None

# Use a second controller if present and distinct from RIGHT.
SECONDARY = LEFT if (LEFT is not None and LEFT is not RIGHT) else None

NOTIFICATION_DIRECTION = 'vertical_up'
APP_TICKER_DIRECTION = 'vertical_up'

# -----------------------------
# WinRT / Windows notifications
# -----------------------------
try:
    from winsdk.windows.foundation.metadata import ApiInformation
    from winsdk.windows.ui.notifications.management import (
        UserNotificationListener,
        UserNotificationListenerAccessStatus,
    )
    from winsdk.windows.ui.notifications import NotificationKinds
except Exception as exc:  # pragma: no cover
    raise SystemExit(
        'Missing WinRT bindings. Install with: pip install winsdk\n'
        f'Import error: {exc}'
    )


@dataclass(frozen=True)
class WatcherConfig:
    poll_seconds: float = 1.0
    kinds: int = int(NotificationKinds.TOAST)
    include_apps: Optional[Set[str]] = None
    exclude_apps: Optional[Set[str]] = None
    print_raw_ids: bool = False
    show_existing_on_start: bool = True

    enable_matrix: bool = True
    matrix_queue_size: int = 5
    matrix_max_chars: int = 140
    matrix_separator: str = ' - '
    matrix_use_thread: bool = True
    matrix_debug: bool = True
    matrix_sanitize: bool = True

    # Scroll tuning
    right_frame_duration: float = 0.01
    secondary_frame_duration: float = 0.01

    # Secondary ticker behavior
    enable_secondary_ticker: bool = True
    secondary_loop: bool = True
    secondary_clear_after: bool = True
    secondary_max_chars: int = 60


class WindowsNotificationWatcher:
    def __init__(self, config: WatcherConfig) -> None:
        self._cfg = config
        self._seen_ids: Set[int] = set()
        self._listener = None

        # Queue items are (right_full_message, secondary_ticker_message)
        self._matrix_queue: Optional[asyncio.Queue[Tuple[str, str]]] = None
        self._matrix_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

        if self._cfg.enable_matrix:
            self._matrix_queue = asyncio.Queue(maxsize=self._cfg.matrix_queue_size)

    async def start(self) -> None:
        self._ensure_supported()

        self._listener = self._get_listener()
        status = await self._listener.request_access_async()

        if status != UserNotificationListenerAccessStatus.ALLOWED:
            raise PermissionError(
                f'Notification access not allowed (status={status}). '
                'If you were not prompted, check Windows Settings → System → Notifications '
                'and ensure notification access is permitted.'
            )

        if self._cfg.enable_matrix and self._matrix_queue is not None:
            self._matrix_task = asyncio.create_task(self._run_matrix_scroller())

        initial = await self._listener.get_notifications_async(self._cfg.kinds)

        if self._cfg.show_existing_on_start:
            for user_notif in initial:
                await self._handle_notification(user_notif, mark_seen=True)
        else:
            for user_notif in initial:
                self._seen_ids.add(int(user_notif.id))

        print('✅ Listening for new notifications... (Ctrl+C to stop)\n')

        try:
            while True:
                await self._poll_once()
                await asyncio.sleep(self._cfg.poll_seconds)
        except KeyboardInterrupt:
            print('\n👋 Stopping...')
        finally:
            await self.stop()

    async def stop(self) -> None:
        self._stop_event.set()

        if self._matrix_task is not None:
            self._matrix_task.cancel()
            try:
                await self._matrix_task
            except asyncio.CancelledError:
                pass

    async def _poll_once(self) -> None:
        notifications = await self._listener.get_notifications_async(self._cfg.kinds)
        for user_notif in notifications:
            notif_id = int(user_notif.id)
            if notif_id in self._seen_ids:
                continue
            await self._handle_notification(user_notif, mark_seen=True)

    async def _handle_notification(self, user_notif, mark_seen: bool) -> None:
        if mark_seen:
            self._seen_ids.add(int(user_notif.id))

        app_identity = self._get_app_identity(user_notif)
        if not self._passes_filters(app_identity):
            return

        lines = self._extract_text_lines(user_notif)

        header = f'[{app_identity}]'
        if self._cfg.print_raw_ids:
            header += f' (id={int(user_notif.id)})'

        print(header)
        for line in lines:
            print(f'  {line}')
        print()

        if self._cfg.enable_matrix and self._matrix_queue is not None:
            right_msg, ticker_msg = self._format_matrix_messages(app_identity, lines)
            self._try_enqueue_matrix(right_msg, ticker_msg)

    def _format_matrix_messages(self, app_identity: str, lines: list[str]) -> Tuple[str, str]:
        # Friendly app name for displays (avoid ids with weird chars)
        friendly_app = app_identity.split(' | ', 1)[0].strip() if app_identity else 'UnknownApp'

        title = lines[0].strip() if lines else ''
        full_text = ' '.join([s.strip() for s in lines if s.strip()])

        right_msg = f'{friendly_app}{self._cfg.matrix_separator}{full_text}'.strip()
        ticker_msg = f'{friendly_app}{self._cfg.matrix_separator}{title}'.strip() if title else friendly_app

        if self._cfg.matrix_sanitize:
            right_msg = self._sanitize_for_matrix(right_msg)
            ticker_msg = self._sanitize_for_matrix(ticker_msg)

        if len(right_msg) > self._cfg.matrix_max_chars:
            right_msg = right_msg[: self._cfg.matrix_max_chars - 3] + '...'

        if len(ticker_msg) > self._cfg.secondary_max_chars:
            ticker_msg = ticker_msg[: self._cfg.secondary_max_chars - 3] + '...'

        return right_msg, ticker_msg

    @staticmethod
    def _sanitize_for_matrix(s: str) -> str:
        replacements = {
            '&': ' and ',
            '|': ' - ',
            '✅': '',
            '✔': '',
            '…': '...',
            '—': '-',
            '–': '-',
            '“': '"',
            '”': '"',
            '‘': "'",
            '’': "'",
            '•': '*',
        }
        for char, replacement in replacements.items():
            s = s.replace(char, replacement)

        s = unicodedata.normalize('NFKD', s)
        s = ''.join(ch for ch in s if not unicodedata.combining(ch))
        s = s.encode('ascii', errors='ignore').decode('ascii')
        s = re.sub(r'[^A-Za-z0-9 \-_\.\,\:\;\!\?\(\)\[\]\'\"\/\+]', ' ', s)
        s = re.sub(r'\s+', ' ', s).strip()
        return s or '(unrenderable)'

    def _try_enqueue_matrix(self, right_msg: str, ticker_msg: str) -> None:
        assert self._matrix_queue is not None
        try:
            self._matrix_queue.put_nowait((right_msg, ticker_msg))
            if self._cfg.matrix_debug:
                print(f'🟩 MATRIX ENQUEUE: right="{right_msg}" | ticker="{ticker_msg}"')
        except asyncio.QueueFull:
            if self._cfg.matrix_debug:
                print('⚠️ MATRIX QUEUE FULL: dropped newest message')

    async def _run_matrix_scroller(self) -> None:
        assert self._matrix_queue is not None

        right_scroll = self._detect_scroll_fn(RIGHT)
        if right_scroll is None:
            print('❌ RIGHT has no scroll_text / scrollText method. Check your controller API.')
            return

        secondary_scroll = None
        if SECONDARY is not None:
            secondary_scroll = self._detect_scroll_fn(SECONDARY)

        if self._cfg.matrix_debug:
            has_secondary_display = 'yes' if (SECONDARY is not None and secondary_scroll is not None) else 'no'
            print(f'🧪 Matrix scroller armed (secondary present: {has_secondary_display})')

        while not self._stop_event.is_set():
            try:
                right_msg, ticker_msg = await asyncio.wait_for(self._matrix_queue.get(), timeout=0.25)
            except asyncio.TimeoutError:
                continue

            if self._cfg.matrix_debug:
                print(f'🟦 MATRIX DEQUEUE: "{right_msg}" | {self._matrix_queue.qsize()} remaining')

            ticker_task: Optional[asyncio.Task] = None

            try:
                # Start secondary loop ticker while RIGHT scroll runs
                if (
                    self._cfg.enable_secondary_ticker
                    and secondary_scroll is not None
                    and SECONDARY is not None
                ):
                    ticker_task = asyncio.create_task(
                        self._run_secondary_ticker(secondary_scroll, ticker_msg)
                    )

                # Scroll full notification on RIGHT (single-run)
                await self._call_scroll(
                    right_scroll,
                    right_msg,
                    loop=False,
                    direction=NOTIFICATION_DIRECTION,
                    frame_duration=self._cfg.right_frame_duration,
                )

            except Exception as exc:
                print(f'❌ Matrix scroll failed: {exc!r}')

            finally:
                # Stop ticker when RIGHT finishes
                if ticker_task is not None:
                    ticker_task.cancel()
                    try:
                        await ticker_task
                    except asyncio.CancelledError:
                        pass

                if self._cfg.secondary_clear_after and SECONDARY is not None:
                    self._try_clear_secondary()

                self._matrix_queue.task_done()

    async def _run_secondary_ticker(self, scroll_fn, ticker_msg: str) -> None:
        await self._call_scroll(
            scroll_fn,
            ticker_msg,
            loop=self._cfg.secondary_loop,
            direction=APP_TICKER_DIRECTION,
            frame_duration=self._cfg.secondary_frame_duration,
        )

    async def _call_scroll(
        self,
        scroll_fn,
        msg: str,
        *,
        loop: bool,
        direction: str,
        frame_duration: float,
    ) -> None:
        """
        Calls scroll_fn with best-effort kwargs. We degrade gracefully:
          1) msg + direction + frame_duration + loop
          2) msg + direction + loop
          3) msg + direction
          4) msg
        """
        kwargs_all_params = {
            'direction': direction,
            'frame_duration': frame_duration,
            'loop': loop,
        }
        kwargs_without_frame_duration = {
            'direction': direction,
            'loop': loop,
        }
        kwargs_direction_only = {
            'direction': direction,
        }

        if self._cfg.matrix_use_thread:
            try:
                await asyncio.to_thread(scroll_fn, msg, **kwargs_all_params)
                return
            except TypeError:
                pass
            try:
                await asyncio.to_thread(scroll_fn, msg, **kwargs_without_frame_duration)
                return
            except TypeError:
                pass
            try:
                await asyncio.to_thread(scroll_fn, msg, **kwargs_direction_only)
                return
            except TypeError:
                pass
            await asyncio.to_thread(scroll_fn, msg)
            return

        try:
            scroll_fn(msg, **kwargs_all_params)
            return
        except TypeError:
            pass
        try:
            scroll_fn(msg, **kwargs_without_frame_duration)
            return
        except TypeError:
            pass
        try:
            scroll_fn(msg, **kwargs_direction_only)
            return
        except TypeError:
            pass
        scroll_fn(msg)

    def _try_clear_secondary(self) -> None:
        if SECONDARY is None:
            return

        # Best-effort: call whatever your controller supports.
        for method_name in ('clear', 'clear_all', 'stop', 'stop_scroll', 'reset'):
            if hasattr(SECONDARY, method_name):
                try:
                    getattr(SECONDARY, method_name)()
                    if self._cfg.matrix_debug:
                        print(f'🧹 SECONDARY.{method_name}()')
                    return
                except Exception:
                    pass

    @staticmethod
    def _detect_scroll_fn(controller):
        if controller is None:
            return None
        if hasattr(controller, 'scroll_text'):
            return controller.scroll_text
        if hasattr(controller, 'scrollText'):
            return controller.scrollText
        return None

    @staticmethod
    def _ensure_supported() -> None:
        type_name = 'Windows.UI.Notifications.Management.UserNotificationListener'
        if not ApiInformation.is_type_present(type_name):
            raise RuntimeError(
                'UserNotificationListener not supported on this Windows version/build.'
            )

    @staticmethod
    def _get_listener():
        if hasattr(UserNotificationListener, 'current'):
            return UserNotificationListener.current
        if hasattr(UserNotificationListener, 'Current'):
            return UserNotificationListener.Current
        if hasattr(UserNotificationListener, 'get_current'):
            return UserNotificationListener.get_current()
        raise AttributeError(
            'No known way to access UserNotificationListener singleton in this WinRT projection.'
        )

    def _passes_filters(self, app_identity: str) -> bool:
        if self._cfg.include_apps is not None and app_identity not in self._cfg.include_apps:
            return False
        if self._cfg.exclude_apps is not None and app_identity in self._cfg.exclude_apps:
            return False
        return True

    @staticmethod
    def _get_app_identity(user_notif) -> str:
        try:
            app_info = user_notif.app_info
        except Exception:
            return 'UnknownApp'

        identity_parts: list[str] = []

        try:
            display_name = app_info.display_info.display_name
            if display_name:
                identity_parts.append(str(display_name))
        except Exception:
            pass

        for attr in ('app_user_model_id', 'appuser_model_id', 'id'):
            try:
                app_model_id = getattr(app_info, attr)
                if app_model_id:
                    identity_parts.append(str(app_model_id))
                    break
            except Exception:
                pass

        return ' | '.join(identity_parts) if identity_parts else 'UnknownApp'

    @staticmethod
    def _extract_text_lines(user_notif) -> list[str]:
        lines: list[str] = []
        try:
            toast = user_notif.notification
            visual = toast.visual
            for binding in visual.bindings:
                for text_el in binding.get_text_elements():
                    text_content = (text_el.text or '').strip()
                    if text_content:
                        lines.append(text_content)
        except Exception:
            pass

        return lines or ['(no text content)']


async def main() -> None:
    watcher_config = WatcherConfig(
        poll_seconds=1.0,
        show_existing_on_start=True,

        enable_matrix=True,
        matrix_queue_size=5,
        matrix_max_chars=140,
        matrix_separator=' - ',
        matrix_use_thread=True,
        matrix_debug=True,
        matrix_sanitize=True,

        right_frame_duration=0.01,
        secondary_frame_duration=0.01,

        enable_secondary_ticker=True,
        secondary_loop=True,
        secondary_clear_after=True,
        secondary_max_chars=60,
    )

    watcher = WindowsNotificationWatcher(watcher_config)
    await watcher.start()


if __name__ == '__main__':
    asyncio.run(main())