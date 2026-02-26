# GitHub Copilot Instructions for IS-Notify

These instructions help GitHub Copilot generate code that is consistent with this project's conventions.

---

## Project Summary

IS-Notify is a Windows-only Python script that polls the WinRT `UserNotificationListener` API for toast notifications and scrolls them on IS-Matrix LED matrix hardware via the `is-matrix-forge` library.

---

## Naming Conventions

- **Variables and parameters**: use full, descriptive names.
  - ✅ `display_name`, `identity_parts`, `text_content`, `watcher_config`, `notification_id`
  - ❌ `dn`, `bits`, `txt`, `cfg`, `n`, `x`
- **Functions and methods**: use `verb_noun` style (`_poll_once`, `_handle_notification`, `_extract_text_lines`).
- **Classes**: `PascalCase` (`WindowsNotificationWatcher`, `WatcherConfig`).
- **Constants**: `UPPER_SNAKE_CASE` (`NOTIFICATION_DIRECTION`, `SECONDARY`).
- **Private members**: prefix with a single underscore (`_seen_ids`, `_matrix_queue`).

---

## Type Annotations

Always annotate function signatures. For example:

```python
async def _handle_notification(self, user_notif, mark_seen: bool) -> None:
    ...

@staticmethod
def _sanitize_for_matrix(raw_text: str) -> str:
    ...
```

---

## Async Patterns

- Use `await` for all WinRT async calls.
- Wrap blocking calls in `asyncio.to_thread()` to avoid blocking the event loop.
- Always handle `asyncio.CancelledError` explicitly (catch, clean up, re-raise or pass depending on context).

---

## Configuration

New runtime settings belong in the `WatcherConfig` frozen dataclass with a descriptive field name and a safe default value. Update `README.md` to document the new field.

---

## Error Handling

- Catch `Exception` only when calling external WinRT/hardware APIs whose exception types are unknown.
- Do not silently swallow exceptions in the main control flow.
- Use `print(f'❌ ...')` for operator-visible error messages consistent with the rest of the file.

---

## Sanitization

When sending text to the LED matrix, always pass it through `_sanitize_for_matrix` if `WatcherConfig.matrix_sanitize` is `True`. This strips non-ASCII characters and special symbols that the matrix hardware cannot render.

---

## Dependencies

Do not add new `pip` dependencies without:
1. Confirming they are available on PyPI.
2. Adding them to the **Prerequisites** table in `README.md`.

---

## Testing

- Mock `winsdk` imports so tests can run on non-Windows machines.
- Use `pytest` and place tests under a `tests/` directory.
- Focus unit tests on pure functions: `_sanitize_for_matrix`, `_passes_filters`, `_format_matrix_messages`, `_get_app_identity`.
