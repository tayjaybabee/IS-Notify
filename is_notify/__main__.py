from __future__ import annotations

import asyncio

from is_notify.config import WatcherConfig
from is_notify.watcher import WindowsNotificationWatcher


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


def run() -> None:
    """Synchronous entry point used by the ``is-notify`` console script."""
    asyncio.run(main())


if __name__ == '__main__':
    run()
