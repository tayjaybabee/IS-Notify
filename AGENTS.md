# AGENTS.md — Guidance for AI Coding Agents

This document describes the IS-Notify codebase conventions so that AI coding agents (GitHub Copilot, Codex, Claude, etc.) can contribute effectively.

---

## Repository Purpose

IS-Notify reads Windows toast notifications via the WinRT `UserNotificationListener` API and scrolls them on IS-Matrix LED matrix displays. The codebase is structured as the `is_notify` package:

| Module | Responsibility |
|---|---|
| `is_notify/config.py` | `WatcherConfig` frozen dataclass — all runtime knobs |
| `is_notify/matrix.py` | Hardware initialisation (`CONTROLLERS`, `RIGHT`, `SECONDARY`) and `MatrixDisplay` class (formatting, sanitising, scrolling) |
| `is_notify/watcher.py` | `WindowsNotificationWatcher` class — WinRT listener, polling, notification handling |
| `is_notify/__main__.py` | `main()` coroutine and `run()` synchronous entry point |
| `notification-reader.py` | Backward-compatible shim — delegates to `is_notify.__main__.run()` |

---

## Code Conventions

### Naming
- Use **full, descriptive names** for all variables, parameters, and functions — avoid single-letter names and cryptic abbreviations.
  - ✅ `display_name`, `identity_parts`, `text_content`, `watcher_config`
  - ❌ `dn`, `bits`, `txt`, `cfg`
- Class names use `PascalCase` (e.g., `WindowsNotificationWatcher`, `WatcherConfig`).
- Private methods and attributes use a leading underscore (e.g., `_poll_once`, `_seen_ids`).
- Module-level constants use `UPPER_SNAKE_CASE` (e.g., `NOTIFICATION_DIRECTION`, `SECONDARY`).

### Types
- All functions must have type annotations for parameters and return values.
- Use `Optional[T]` or `T | None` (both are valid since the project requires Python 3.11+).
- Use `Set`, `Tuple`, `list` etc. from the standard `typing` module where needed for backward compatibility, or use built-in generics (`set[str]`, `tuple[str, ...]`) — both forms are acceptable in Python 3.11+.

### Error handling
- Use specific exception types where possible; catch bare `Exception` only when truly necessary (e.g., calling external WinRT methods whose exact exceptions are unknown).
- Never silently swallow exceptions in the main control flow — log or re-raise.

### Async
- All I/O-bound operations that touch WinRT use `await`.
- Blocking scroll calls are dispatched via `asyncio.to_thread()` when `matrix_use_thread=True`.
- `asyncio.CancelledError` is always re-raised after cleanup.

---

## Adding Features

1. **New configuration knobs** → add a field to `WatcherConfig` in `is_notify/config.py` with a sensible default and update `README.md`.
2. **New display behaviour** → add a method to `MatrixDisplay` in `is_notify/matrix.py` following the `_verb_noun` naming pattern (e.g., `_run_secondary_ticker`).
3. **New notification-handling behaviour** → add a method to `WindowsNotificationWatcher` in `is_notify/watcher.py`.
4. **Utility/static helpers** → prefer `@staticmethod` on the relevant class; otherwise a module-level function is acceptable.

---

## Testing

There is currently no automated test suite. When writing tests:
- Mock `winsdk` imports at the module level (they are Windows-only).
- Mock `is_matrix_forge` imports similarly to avoid hardware calls on import.
- Test `MatrixDisplay.sanitize_for_matrix`, `MatrixDisplay.format_messages`, `WindowsNotificationWatcher._passes_filters`, and `WindowsNotificationWatcher._get_app_identity` as pure/static logic without WinRT or hardware dependencies.
- Place test files in a `tests/` directory and use `pytest`.

---

## Out of Scope

- Do **not** add support for non-Windows notification APIs in this repository.
- Do **not** introduce new third-party dependencies without updating `README.md` prerequisites.
- Do **not** collapse the package back into a single file.
