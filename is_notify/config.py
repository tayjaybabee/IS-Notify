from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Set

try:
    from winsdk.windows.ui.notifications import NotificationKinds as _NotificationKinds
    _DEFAULT_KINDS: int = int(_NotificationKinds.TOAST)
except Exception:
    _DEFAULT_KINDS = 4  # NotificationKinds.TOAST


@dataclass(frozen=True)
class WatcherConfig:
    poll_seconds: float = 1.0
    kinds: int = _DEFAULT_KINDS
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
