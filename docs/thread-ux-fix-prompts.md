# Thread UX + Browser State Isolation Prompt Pack

This pack targets the exact regressions reported in screenshots:
1) browser frame leaks across users/threads,
2) generic thread titles,
3) noisy chat artifacts (`(no tool call):`, status spam),
4) browser actions leaking into chat (`go back` etc.),
5) state corruption after refresh/thread switch,
6) shell cards degrading into plain text after reload.

---

## Prompt T1 — Per-user/per-thread browser frame isolation

```md
Task: Scope browser frame state by BOTH user and thread so frames never leak globally.

Problem to solve:
- Last browser screenshot/frame persists across different threads and even different accounts.

Requirements:
1) Replace any global `latestFrame` rendering source with keyed state:
   - key = `${userId}:${threadId}`
2) On thread switch:
   - load frame only for selected thread key
   - do NOT fallback to previous thread frame
3) On account switch/logout:
   - clear in-memory frame cache
4) Persist frame snapshots per thread in conversation storage (server-side message metadata or client cache keyed by user/thread).
5) Ensure WebSocket frame events update only active thread key.

Likely files:
- frontend/src/hooks/useWebSocket.ts
- frontend/src/App.tsx
- frontend/src/hooks/useConversations.ts
- main.py / backend conversation persistence paths (if server metadata needed)

Acceptance:
- Switching threads never shows another thread's frame.
- Switching user accounts never shows prior account frame.
- Returning to a thread restores only that thread's last frame.
```

How this solves it:
- Eliminates single global frame state and enforces strict user+thread scoping.

---

## Prompt T2 — Thread title must be first triggering prompt

```md
Task: Use first task-triggering prompt as canonical thread title (replace generic defaults).

Problem to solve:
- Threads display generic names like "New web conversation".

Requirements:
1) At first user instruction that starts work (`navigate` or equivalent), set conversation title = first prompt (trimmed).
2) Only auto-title when title is still default/empty.
3) Never overwrite with later tool/status messages.
4) Keep channel-specific fallback titles (Telegram/Slack/Discord) only when no user prompt exists.
5) Ensure frontend task list reflects updated server title immediately.

Likely files:
- backend/conversation_service.py
- main.py
- frontend/src/hooks/useConversations.ts
- frontend/src/App.tsx (task history merge)

Acceptance:
- Newly started thread title equals first trigger prompt.
- Generic defaults disappear once first prompt is sent.
```

How this solves it:
- Promotes user intent as stable title and removes platform-generic naming.

---

## Prompt T3 — Ban noise strings + align thinking row layout

```md
Task: Remove noisy status artifacts from chat and fix thinking-row horizontal alignment.

Problems to solve:
- `(no tool call):` appears in chat.
- `Session settings updated` appears in chat.
- Thinking row/logo is visually indented too far.

Requirements:
1) Add hard chat filters for exact noise patterns:
   - `(no tool call):`
   - `Model response (no tool call):`
   - `Session settings updated`
   - `Workflow step update`
2) Keep these events in Action Log only where appropriate (or suppress entirely if non-user-facing).
3) Update thinking row container spacing so avatar/tag aligns with other assistant rows.
4) Add visual regression test/snapshot for thinking row left margin/padding.

Likely files:
- frontend/src/components/ChatPanel.tsx
- frontend/src/components/ActionLog.tsx
- frontend styles/tailwind classes in ChatPanel thinking row component

Acceptance:
- `(no tool call):` never appears in chat.
- Session/workflow noise does not appear in chat.
- Thinking row aligns with other assistant content columns.
```

How this solves it:
- Enforces explicit deny-list filtering and fixes the row spacing mismatch causing visual drift.

---

## Prompt T4 — Browser actions must NEVER appear in chat (including go_back)

```md
Task: Enforce permanent browser-action exclusion from chat, including historical reload paths.

Problem to solve:
- Browser actions like `go back` slip into chat (live or after thread reload).

Requirements:
1) Expand browser-only tool set to include all browser primitives (`go_back` included explicitly).
2) Apply filtering in TWO places:
   - live websocket log->chat mapping,
   - hydrated server message->chat mapping (reload/switch path)
3) Introduce shared helper `isBrowserOnlyEvent(...)` used by both mappings.
4) Add test fixtures with historical messages containing `[go_back]`, `[click]`, `[go_to_url]` to confirm exclusion.

Likely files:
- frontend/src/components/ChatPanel.tsx
- frontend/src/hooks/useConversations.ts
- frontend/src/hooks/useWebSocket.ts

Acceptance:
- Browser actions never render in chat in live session.
- Browser actions never render after refresh/thread switch/history hydrate.
- Action Log still shows full browser workflow.
```

How this solves it:
- Closes the dual-path bug (live filter vs hydration filter mismatch).

---

## Prompt T5 — Persist normalized chat view model (prevent post-refresh scatter)

```md
Task: Persist normalized message model per thread so UI state does not degrade after reload.

Problems to solve:
- After refresh/switch, chat rehydrates as raw workflow spam.
- Previously filtered content reappears.

Requirements:
1) Build canonical message normalizer producing typed UI model:
   - user
   - assistant_summary
   - tool_shell
   - thinking
   - ask_user_input
2) Persist normalized thread view-model snapshot keyed by user+thread.
3) Rehydrate from normalized model first; merge new server events with idempotent reducer.
4) Ignore stale/duplicate workflow events on hydrate.

Likely files:
- frontend/src/components/ChatPanel.tsx
- frontend/src/hooks/useConversations.ts
- frontend/src/hooks/useWebSocket.ts

Acceptance:
- Chat looks identical before and after refresh.
- Browser workflow spam never returns after switching away/back.
```

How this solves it:
- Prevents raw-event re-interpretation drift by storing stable UI-ready messages.

---

## Prompt T6 — Preserve shell card structure across reload/thread switch

```md
Task: Keep non-browser tool outputs as shell accordion cards after reload (not plain text fallback).

Problem to solve:
- Shell cards collapse into plain text when thread is rehydrated.

Requirements:
1) Persist structured tool message fields for non-browser tools:
   - toolName
   - command/args
   - result
   - status
   - timestamp
2) On hydrate, reconstruct `role: tool` cards from structured fields, not raw text lines.
3) Keep default collapsed/expanded behavior deterministic on reload.
4) Add migration path for legacy raw-text entries (best-effort parsing).

Likely files:
- frontend/src/components/ChatPanel.tsx
- backend message persistence format (if needed)
- frontend/src/hooks/useConversations.ts

Acceptance:
- Non-browser tool history renders as shell accordion cards after reload.
- No downgrade to plain text for previously structured tool events.
```

How this solves it:
- Ensures card rendering depends on stable structured data, not brittle raw text parsing.

---

## Master execution prompt (T1→T6)

```md
Implement T1 through T6 from docs/thread-ux-fix-prompts.md in strict order.
Stop on any failed acceptance gate.
After each step provide:
1) changed files,
2) commands/tests run,
3) pass/fail checklist,
4) residual risks.
```
