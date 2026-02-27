# IS-Notify

A Windows notification reader that intercepts system toast notifications and scrolls them across IS-Matrix LED matrix displays using the [IS-Matrix-Forge](https://github.com/tayjaybabee/IS-Matrix-Forge) library.

## Overview

IS-Notify polls the Windows `UserNotificationListener` API for toast notifications and displays them on one or two connected LED matrix controllers:

- **Primary (right) display** — scrolls the full notification text (app name + all text lines).
- **Secondary (left) display** — simultaneously scrolls a short ticker showing just the app name and notification title while the primary display runs.

## Prerequisites

| Requirement | Details |
|---|---|
| OS | Windows 10 (build 18362+) or Windows 11 |
| Python | 3.11+ |
| [Poetry](https://python-poetry.org/) | Recommended for dependency and virtual environment management |
| [`winsdk`](https://pypi.org/project/winsdk/) | WinRT Python bindings |
| [`is-matrix-forge`](https://pypi.org/project/is-matrix-forge/) | IS-Matrix LED matrix controller library |

## Installation

Clone the repository and install dependencies with [Poetry](https://python-poetry.org/):

```bash
git clone https://github.com/tayjaybabee/IS-Notify.git
cd IS-Notify
poetry install
```

Poetry will create an isolated virtual environment and install `winsdk` and `is-matrix-forge` automatically.

> **Note:** `winsdk` is a Windows-only package and will only be installed when running on Windows.

### Alternative: pip

```bash
pip install winsdk is-matrix-forge
```

## Usage

Run the notification reader with Poetry:

```bash
poetry run python notification-reader.py
```

Or, if you are already inside the Poetry shell (`poetry shell`), run it directly:

```bash
python notification-reader.py
```

On first run, Windows will prompt you to grant notification access. Accept the prompt, or manually enable it in **Settings → System → Notifications → Notification access**.

Press **Ctrl+C** to stop.

## Configuration

All runtime options are controlled by the `WatcherConfig` dataclass at the bottom of `notification-reader.py`. Edit the `main()` function to change defaults:

```python
watcher_config = WatcherConfig(
    poll_seconds=1.0,           # How often (seconds) to poll for new notifications
    show_existing_on_start=True,# Display notifications already present at startup

    # --- Matrix display ---
    enable_matrix=True,         # Enable LED matrix output
    matrix_queue_size=5,        # Max notifications buffered for scrolling
    matrix_max_chars=140,       # Truncate primary display message to this length
    matrix_separator=' - ',     # String placed between app name and message text
    matrix_use_thread=True,     # Run scroll calls in a background thread
    matrix_debug=True,          # Print debug info about queue and scroll events
    matrix_sanitize=True,       # Strip non-ASCII / special characters before display

    # --- Scroll tuning ---
    right_frame_duration=0.01,      # Seconds per frame on the primary display
    secondary_frame_duration=0.01,  # Seconds per frame on the secondary display

    # --- Secondary ticker ---
    enable_secondary_ticker=True,   # Enable the secondary (left) display ticker
    secondary_loop=True,            # Loop the secondary ticker continuously
    secondary_clear_after=True,     # Clear secondary display after primary finishes
    secondary_max_chars=60,         # Truncate secondary ticker message to this length

    # --- Filtering ---
    include_apps=None,  # Set[str] of app names to allow (None = allow all)
    exclude_apps=None,  # Set[str] of app names to block (None = block none)
)
```

### Filtering notifications

To show only specific apps:

```python
include_apps={'Slack', 'Microsoft Teams'},
```

To suppress specific apps:

```python
exclude_apps={'Windows Security', 'Microsoft Store'},
```

## Project Structure

```
IS-Notify/
├── notification-reader.py   # Main script: watcher, config, and entry point
├── pyproject.toml           # Poetry project configuration and dependencies
├── README.md
├── AGENTS.md
├── .github/
│   └── copilot-instructions.md
└── LICENSE
```

## License

See [LICENSE](LICENSE).
