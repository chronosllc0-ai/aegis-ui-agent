# Integrations Capability Matrix

| Capability | Slack | Discord | Notes |
|---|---|---|---|
| oauth_connect | supported | planned | Slack uses existing OAuth connector scaffolding; Discord remains bot-token based. |
| webhook_events | supported | supported | Both adapters now expose `handle_event` normalization entrypoint. |
| slash/app_commands | supported | supported | Slack interaction payloads + Discord application interactions mapped to canonical envelopes. |
| send_text | supported | supported | `send_text` contract method implemented for both adapters. |
| edit_text | supported | supported | Slack via `chat.update`; Discord via `PATCH /channels/{channel}/messages/{message_id}`. |
| send_file | supported | supported | Slack external upload flow + Discord multipart attachments. |
| send_image | partial | supported | Slack image is supported through generic file upload path; Discord has explicit image helper wrapper. |
| stream_update_safe | supported | supported | Edit pathways include rate-limit aware retries for progressive updates. |
| rate_limit_policy | supported | supported | Automatic backoff on HTTP 429 with provider-specific retry hints. |
| idempotency_handling | supported | supported | In-memory delivery-id dedupe on repeated webhook deliveries. |
| error_normalization | partial | partial | Both adapters normalize transport errors, but richer shared error taxonomy is still planned. |
