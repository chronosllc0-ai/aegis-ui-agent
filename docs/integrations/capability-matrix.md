# Integrations Capability Matrix

Status legend:
- **supported**: native wrapper exists and is routed directly.
- **partial**: available only through equivalent fallback path.
- **unsupported**: no platform-equivalent; routed to graceful fallback reply.

| Capability | Telegram | Slack | Discord | Notes |
|---|---|---|---|---|
| send_text | supported | supported | supported | Canonical send wrapper on all three adapters. |
| edit_message | supported | supported | supported | Slack `chat.update`; Discord PATCH; Telegram `editMessageText`. |
| delete_message | supported | supported | supported | Slack `chat.delete`; Discord DELETE message; Telegram `deleteMessage`. |
| react | supported | supported | supported | Slack `reactions.add`; Discord reaction endpoint; Telegram `setMessageReaction`. |
| send_file | supported | supported | supported | Slack external-upload flow; Discord multipart upload; Telegram `sendDocument`. |
| interactive_actions | supported | supported | supported | Telegram inline keyboard; Slack buttons/select blocks; Discord components (buttons/select). |
| command_controls | supported | supported | supported | Telegram callback payloads + Slack slash-command equivalents + Discord app commands. |
| runtime_control_components | partial | supported | supported | Telegram uses inline fallback semantics; Slack/Discord provide dedicated component builders. |
| topic_threads | supported | unsupported | unsupported | Telegram forum topics only; Slack/Discord route to graceful fallback message. |
| native_poll | supported | unsupported | unsupported | Telegram poll tool exists; Slack/Discord currently fallback. |

## Fallback behavior

Capability status is evaluated through `backend.integrations.capability_matrix.CAPABILITY_MATRIX` and `TOOL_CAPABILITY_MAP`.
When a Slack/Discord tool call is not mapped as `supported`, adapters return a graceful normalized fallback payload:

```json
{
  "ok": false,
  "fallback": true,
  "error": "<tool> is <status> on <platform>; returning graceful fallback."
}
```
