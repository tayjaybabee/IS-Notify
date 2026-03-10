from __future__ import annotations

import asyncio
import inspect
import re
import unicodedata
from typing import Optional, Tuple

from is_matrix_forge.led_matrix.controller import get_controllers
from is_matrix_forge.led_matrix.controller.helpers import find_leftmost, find_rightmost

from is_notify.config import WatcherConfig

# Direction constants for scroll animations
NOTIFICATION_DIRECTION = 'vertical_up'
APP_TICKER_DIRECTION = 'vertical_up'

# -----------------------------
# Hardware initialisation
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


class MatrixDisplay:
    """Manages formatting and display of notifications on IS-Matrix LED controllers."""

    def __init__(self, config: WatcherConfig, stop_event: asyncio.Event) -> None:
        self._config = config
        self._stop_event = stop_event
        self._queue: asyncio.Queue[Tuple[str, str]] = asyncio.Queue(
            maxsize=config.matrix_queue_size
        )

    @property
    def queue(self) -> asyncio.Queue[Tuple[str, str]]:
        return self._queue

    def format_messages(self, app_identity: str, lines: list[str]) -> Tuple[str, str]:
        """Return ``(right_full_message, secondary_ticker_message)`` ready for display."""
        friendly_app = app_identity.split(' | ', 1)[0].strip() if app_identity else 'UnknownApp'

        title = lines[0].strip() if lines else ''
        full_text = ' '.join([s.strip() for s in lines if s.strip()])

        right_msg = f'{friendly_app}{self._config.matrix_separator}{full_text}'.strip()
        ticker_msg = (
            f'{friendly_app}{self._config.matrix_separator}{title}'.strip()
            if title
            else friendly_app
        )

        if self._config.matrix_sanitize:
            right_msg = self.sanitize_for_matrix(right_msg)
            ticker_msg = self.sanitize_for_matrix(ticker_msg)

        if len(right_msg) > self._config.matrix_max_chars:
            right_msg = right_msg[: self._config.matrix_max_chars - 3] + '...'

        if len(ticker_msg) > self._config.secondary_max_chars:
            ticker_msg = ticker_msg[: self._config.secondary_max_chars - 3] + '...'

        return right_msg, ticker_msg

    @staticmethod
    def sanitize_for_matrix(raw_text: str) -> str:
        """Strip or replace characters that the LED matrix hardware cannot render."""
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
            raw_text = raw_text.replace(char, replacement)

        raw_text = unicodedata.normalize('NFKD', raw_text)
        raw_text = ''.join(ch for ch in raw_text if not unicodedata.combining(ch))
        raw_text = raw_text.encode('ascii', errors='ignore').decode('ascii')
        raw_text = re.sub(r'[^A-Za-z0-9 \-_\.\,\:\;\!\?\(\)\[\]\'\"\/\+]', ' ', raw_text)
        raw_text = re.sub(r'\s+', ' ', raw_text).strip()
        return raw_text or '(unrenderable)'

    def try_enqueue(self, right_msg: str, ticker_msg: str) -> None:
        """Put a message pair on the display queue, dropping it if the queue is full."""
        try:
            self._queue.put_nowait((right_msg, ticker_msg))
            if self._config.matrix_debug:
                print(f'🟩 MATRIX ENQUEUE: right="{right_msg}" | ticker="{ticker_msg}"')
        except asyncio.QueueFull:
            if self._config.matrix_debug:
                print('⚠️ MATRIX QUEUE FULL: dropped newest message')

    async def run_scroller(self) -> None:
        """Consume the display queue and scroll each message on the matrix hardware."""
        right_scroll = self.detect_scroll_fn(RIGHT)
        if right_scroll is None:
            print('❌ RIGHT has no scroll_text / scrollText method. Check your controller API.')
            return

        secondary_scroll = None
        if SECONDARY is not None:
            secondary_scroll = self.detect_scroll_fn(SECONDARY)

        if self._config.matrix_debug:
            has_secondary_display = SECONDARY is not None and secondary_scroll is not None
            print(
                f'🧪 Matrix scroller armed '
                f'(secondary present: {"yes" if has_secondary_display else "no"})'
            )

        while not self._stop_event.is_set():
            try:
                right_msg, ticker_msg = await asyncio.wait_for(
                    self._queue.get(), timeout=0.25
                )
            except asyncio.TimeoutError:
                continue

            if self._config.matrix_debug:
                print(f'🟦 MATRIX DEQUEUE: "{right_msg}" | {self._queue.qsize()} remaining')

            ticker_task: Optional[asyncio.Task] = None

            try:
                # Start secondary loop ticker while RIGHT scroll runs.
                if (
                    self._config.enable_secondary_ticker
                    and secondary_scroll is not None
                    and SECONDARY is not None
                ):
                    ticker_task = asyncio.create_task(
                        self._run_secondary_ticker(secondary_scroll, ticker_msg)
                    )

                # Scroll full notification on RIGHT (single-run).
                await self._call_scroll(
                    right_scroll,
                    right_msg,
                    loop=False,
                    direction=NOTIFICATION_DIRECTION,
                    frame_duration=self._config.right_frame_duration,
                )

            except Exception as exc:
                print(f'❌ Matrix scroll failed: {exc!r}')

            finally:
                # Stop ticker when RIGHT finishes.
                if ticker_task is not None:
                    ticker_task.cancel()
                    try:
                        await ticker_task
                    except asyncio.CancelledError:
                        pass

                if self._config.secondary_clear_after and SECONDARY is not None:
                    self._try_clear_secondary()

                self._queue.task_done()

    async def _run_secondary_ticker(self, scroll_fn, ticker_msg: str) -> None:
        await self._call_scroll(
            scroll_fn,
            ticker_msg,
            loop=self._config.secondary_loop,
            direction=APP_TICKER_DIRECTION,
            frame_duration=self._config.secondary_frame_duration,
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
        Call scroll_fn passing only the kwargs its signature actually accepts,
        determined ahead of time via inspect.signature to avoid masking TypeErrors
        raised from inside the function body.
        """
        all_kwargs = {
            'direction': direction,
            'frame_duration': frame_duration,
            'loop': loop,
        }

        try:
            accepted_params = inspect.signature(scroll_fn).parameters
            accepted_kwargs = {k: v for k, v in all_kwargs.items() if k in accepted_params}
        except (ValueError, TypeError):
            # Signature not introspectable (e.g. built-in); pass no extra kwargs.
            accepted_kwargs = {}

        if self._config.matrix_use_thread:
            await asyncio.to_thread(scroll_fn, msg, **accepted_kwargs)
            return

        scroll_fn(msg, **accepted_kwargs)

    def _try_clear_secondary(self) -> None:
        if SECONDARY is None:
            return

        # Best-effort: call whatever method the controller supports.
        for method_name in ('clear', 'clear_all', 'stop', 'stop_scroll', 'reset'):
            if hasattr(SECONDARY, method_name):
                try:
                    getattr(SECONDARY, method_name)()
                    if self._config.matrix_debug:
                        print(f'🧹 SECONDARY.{method_name}()')
                    return
                except Exception:
                    pass

    @staticmethod
    def detect_scroll_fn(controller):
        """Return the scroll callable for *controller*, or ``None`` if not found."""
        if controller is None:
            return None
        if hasattr(controller, 'scroll_text'):
            return controller.scroll_text
        if hasattr(controller, 'scrollText'):
            return controller.scrollText
        return None
