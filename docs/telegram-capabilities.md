# Telegram capabilities (official Bot API methods)

This integration intentionally uses official Telegram Bot API methods only (no custom pseudo-methods in runtime logic).

## Tested method set

- `getMe`
- `setWebhook`
- `deleteWebhook`
- `getUpdates`
- `setMyCommands`
- `sendMessage`
- `editMessageText`
- `sendChatAction`
- `answerCallbackQuery`
- `sendPhoto`
- `sendDocument`
- `setChatAdministratorCustomTitle` (legacy alias compatibility mapper)

## Migration compatibility mapper (temporary)

Legacy pseudo-actions are supported short-term and mapped internally:

- `send_message_draft` → `editMessageText`
- `set_chat_member_tag` → `setChatAdministratorCustomTitle`

Every mapper use emits a deprecation warning log and increments in-memory telemetry counters.

## Versioning approach

The integration does not hardcode a Telegram Bot API version string at runtime.

Compatibility is maintained by:

1. implementing official documented methods,
2. keeping this tested method set current,
3. verifying behavior through CI tests in `tests/test_telegram.py`.
