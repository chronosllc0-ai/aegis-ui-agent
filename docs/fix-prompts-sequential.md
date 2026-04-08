# Aegis Fix Prompts — Sequential, No-Skip Execution Plan

Use these prompts in order. Do **not** skip a phase. Each phase has strict acceptance gates; if a gate fails, do not continue to the next phase.

## Phase 0 — Baseline + safety guardrails

```md
Task: Create a baseline branch checkpoint and add temporary debug telemetry for message/event routing.

Requirements:
1) Add scoped debug logs (frontend-only dev mode) for:
   - incoming ws event payload type
   - derived chat message role/type
   - dedupe key decisions (insert/update/drop)
2) Add a small “event trace id” field in normalized message objects (non-UI) for troubleshooting.
3) Ensure logs are disabled in production build.

Acceptance:
- Frontend build passes.
- Running app in dev shows event-to-chat mapping traces.
- No visible UI changes in production mode.
```

---

## Phase 1 — Remove browser-panel composer (must be fully complete before continuing)

```md
Task: Ensure browser panel has no InputBar composer and chat remains sole composition surface.

Requirements:
1) Remove/hide browser-mode InputBar render path entirely.
2) Preserve browser controls: URL/navigation controls, ScreenView, ActionLog, stop button.
3) Confirm no broken send paths:
   - chat send still works
   - steer/interrupt/queue behavior still works from chat composer
4) Remove dead imports/state created only for the browser InputBar path.

Files likely:
- frontend/src/App.tsx
- frontend/src/components/InputBar.tsx (only if cleanup needed)

Acceptance:
- Browser panel renders without composer on desktop/mobile.
- Chat composer remains fully functional.
- TypeScript build passes with no unused symbol regressions.
```

---

## Phase 2 — Chat vs ActionLog routing hardening (browser noise must never leak)

```md
Task: Route browser workflow chatter to ActionLog only; keep chat narrative clean.

Requirements:
1) In chat filtering logic, suppress browser-only traces including:
   - Session settings updated
   - Workflow step update
   - Starting task:
   - terminal task chatter (Task completed/interrupted/failed) unless explicit final summary event
   - raw browser tool traces ([go_to_url], [extract_page], [click], [wait], etc.)
2) Keep non-browser tools visible as shell/tool cards in chat.
3) Prevent duplicate rendering across ActionLog and chat.
4) Add tests for routing behavior.

Files likely:
- frontend/src/components/ChatPanel.tsx
- frontend/src/App.tsx
- frontend tests related to message mapping

Acceptance:
- Browser telemetry appears in ActionLog only.
- Chat shows user intent + meaningful assistant summaries.
- Tests pass for routing filters and dedupe behavior.
```

---

## Phase 3 — Plan card dedupe + JSON/object payload rendering fix

```md
Task: Fix plan-card duplication and render plan payloads as readable structured content.

Symptoms:
- plan card appears twice
- raw object fragments like {"content": ...} render directly
- implement click can look visually stalled

Requirements:
1) Add canonical plan event normalizer that handles string/object/stringified JSON safely.
2) Build deterministic dedupe key (task_id + request_id + plan_hash).
3) Render plan body as markdown bullets/checklist when payload is structured.
4) Add idempotent handling for Implement/Confirm actions to avoid duplicate transitions.
5) Preserve stream continuity after implement click (no frozen state).

Files likely:
- frontend/src/components/ChatPanel.tsx
- frontend/src/hooks/useWebSocket.ts
- optional helper: frontend/src/lib/planFormatting.ts

Acceptance:
- Same plan event no longer creates duplicate cards.
- No raw JSON object leakage in plan card UI.
- Implement action transitions reliably and streaming continues.
```

---

## Phase 4 — Streaming normalization pipeline (web + outbound channels)

```md
Task: Normalize streamed output incrementally and prevent malformed token artifacts.

Requirements:
1) Build shared stream normalizer for:
   - escaped newline variants (/n, \\n)
   - malformed control tokens
   - partial markdown/code fence stability during chunked streaming
2) Suppress raw control markers (e.g., [thinking]) from final chat text.
3) Add final reconciliation pass when stream completes.
4) Add adapters for outbound channels:
   - Telegram escape strategy
   - Slack mrkdwn-safe formatting
   - Discord markdown-safe payload

Files likely:
- frontend/src/hooks/useWebSocket.ts
- frontend/src/components/ChatPanel.tsx
- integrations/telegram.py
- integrations/slack_connector.py
- integrations/discord.py

Acceptance:
- Web stream is coherent and readable while live.
- No raw control tokens shown to users.
- Channel outputs are correctly escaped/formatted.
```

---

## Phase 5 — UI state continuity + idempotent reducer (no DB migration first)

```md
Task: Stabilize in-flight UI state with deterministic reconciliation, without immediate datastore migration.

Requirements:
1) Introduce monotonic event sequencing or event IDs for client merge logic.
2) Add reducer-based state reconciliation:
   - insert/update/replace by event identity
   - ignore stale/out-of-order duplicates
3) Persist task-scoped in-flight UI state locally (session/task keyed) so view resumes correctly.
4) Keep Postgres as persisted history source-of-truth; do not add Redis unless justified by fanout needs.

Acceptance:
- Returning to a task does not scatter/duplicate event presentation.
- Mid-task transitions (plan->implement->stream) remain continuous.
- Duplicate/out-of-order events no longer corrupt UI state.
```

---

## Phase 6 — Brand/logo visual correctness + activity ring

```md
Task: Fix shield asset transparency and add generation-state activity ring.

Requirements:
1) Replace shield asset with transparent-background source.
2) Ensure app-wide usage of the same asset (header + assistant origin marker).
3) Add branded activity ring animation around shield during thinking/streaming.
4) Idle state should show static shield with no ring.
5) Validate dark mode/mobile scaling.

Files likely:
- frontend/public/* asset files
- frontend/src/components/icons.tsx
- frontend/src/App.tsx
- frontend/src/components/ChatPanel.tsx
- relevant CSS/Tailwind utilities

Acceptance:
- No black square backgrounds remain.
- Ring appears only during active generation/thinking.
- Visual regression check complete.
```

---

## Phase 7 — Regression suite + release checklist (must pass before merge)

```md
Task: Add/expand regression tests for all phases and run full validation.

Required tests:
1) Browser-noise routing tests (chat exclusion + ActionLog inclusion).
2) Plan dedupe + structured payload render tests.
3) Thinking/control-token suppression tests.
4) Browser-panel InputBar absence test.
5) Stream normalization tests for escaped newline/control artifacts.
6) Optional snapshot/visual test for logo transparency + activity ring state toggles.

Validation commands:
- frontend build
- targeted frontend tests
- backend tests touching stream/channel formatters

Acceptance:
- All tests green.
- No new TypeScript or lint regressions.
- PR summary includes before/after behavior for each phase.
```

---

## One-pass “execute all phases” master prompt

```md
Execute Phases 0 through 7 from docs/fix-prompts-sequential.md in strict order. Do not skip any phase. After each phase:
1) summarize changed files,
2) list acceptance checks run and outcomes,
3) stop if any gate fails and provide remediation diff before continuing.

When complete, provide:
- final changed-file list by phase,
- test matrix with pass/fail,
- known residual risks,
- rollout notes.
```
