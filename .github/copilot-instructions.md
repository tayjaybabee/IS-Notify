# GitHub Copilot Instructions for IS-Notify

The canonical conventions for this project — naming, types, async patterns, error handling,
adding features, testing, and out-of-scope items — are documented in [`AGENTS.md`](../AGENTS.md).
Please read that file first; the sections below add only Copilot-specific guidance.

---

## Type Annotation Examples

Always annotate function signatures. For example:

```python
async def _handle_notification(self, user_notif, mark_seen: bool) -> None:
    ...

@staticmethod
def _sanitize_for_matrix(raw_text: str) -> str:
    ...
```

---

## Error Message Style

Use `print(f'❌ ...')` for operator-visible error messages, consistent with the rest of the
file. Do not raise unhandled exceptions from display/scroll paths.

---

## Sanitization Reminder

When generating text for the LED matrix, always pass it through `_sanitize_for_matrix` when
`WatcherConfig.matrix_sanitize` is `True`. This strips non-ASCII characters and special symbols
that the matrix hardware cannot render.

---

## Configuration Changes

New runtime settings belong in the `WatcherConfig` frozen dataclass. Always update
`README.md` to document the new field alongside the existing config reference table.
