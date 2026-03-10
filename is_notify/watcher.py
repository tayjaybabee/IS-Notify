from __future__ import annotations

import asyncio
from typing import Optional, Set

from is_notify.config import WatcherConfig
from is_notify.matrix import MatrixDisplay

try:
    from winsdk.windows.foundation.metadata import ApiInformation
    from winsdk.windows.ui.notifications.management import (
        UserNotificationListener,
        UserNotificationListenerAccessStatus,
    )
except Exception as exc:  # pragma: no cover
    raise SystemExit(
        'Missing WinRT bindings. Install with: pip install winsdk\n'
        f'Import error: {exc}'
    )


class WindowsNotificationWatcher:
    def __init__(self, config: WatcherConfig) -> None:
        self._config = config
        self._seen_ids: Set[int] = set()
        self._listener = None
        self._stop_event = asyncio.Event()
        self._matrix: Optional[MatrixDisplay] = None
        self._matrix_task: Optional[asyncio.Task] = None

        if self._config.enable_matrix:
            self._matrix = MatrixDisplay(self._config, self._stop_event)

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

        if self._config.enable_matrix and self._matrix is not None:
            self._matrix_task = asyncio.create_task(self._matrix.run_scroller())

        initial = await self._listener.get_notifications_async(self._config.kinds)

        if self._config.show_existing_on_start:
            for user_notif in initial:
                await self._handle_notification(user_notif, mark_seen=True)
        else:
            for user_notif in initial:
                self._seen_ids.add(int(user_notif.id))

        print('✅ Listening for new notifications... (Ctrl+C to stop)\n')

        try:
            while True:
                await self._poll_once()
                await asyncio.sleep(self._config.poll_seconds)
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
        notifications = await self._listener.get_notifications_async(self._config.kinds)
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
        if self._config.print_raw_ids:
            header += f' (id={int(user_notif.id)})'

        print(header)
        for line in lines:
            print(f'  {line}')
        print()

        if self._config.enable_matrix and self._matrix is not None:
            right_msg, ticker_msg = self._matrix.format_messages(app_identity, lines)
            self._matrix.try_enqueue(right_msg, ticker_msg)

    def _passes_filters(self, app_identity: str) -> bool:
        if self._config.include_apps is not None and app_identity not in self._config.include_apps:
            return False
        if self._config.exclude_apps is not None and app_identity in self._config.exclude_apps:
            return False
        return True

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
