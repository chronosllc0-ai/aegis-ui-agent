# Modes as System-Level Nodes — Prompt Pack (Missing Pieces)

This pack addresses the missing implementation areas for the new Modes feature:
- backend completion (authoritative enforcement),
- admin settings instruction UI,
- orchestrator-as-router behavior,
- integration UX parity (`/mode` + inline picker),
- standards-aligned security/feasibility checks.

---

## Prompt M1 — Canonical mode model + immutable system-node policy

```md
Task: Treat modes as immutable system-level nodes controlled only by admins.

Goal:
- Modes are not user-editable/deletable.
- Runtime always resolves mode policy server-side.

Requirements:
1) Canonical mode registry (single source of truth):
   - orchestrator
   - planner
   - architect
   - deep_research
   - code
2) Mark all mode definitions as system-owned/immutable.
3) Add server-side enforcement:
   - user requests cannot create/delete/rename modes,
   - user requests cannot change protected mode policy fields.
4) Persist only admin-editable per-mode instruction text and optional safe metadata.
5) Add audit events for admin edits.

Implementation hints (repo):
- backend/modes.py (extend policy shape)
- backend/admin/* (new admin routes/service)
- main.py (validate incoming mode config)

Acceptance:
- Any non-admin attempt to mutate system modes is rejected server-side.
- Mode registry remains stable across restarts.
- Audit log contains admin instruction edits.
```

---

## Prompt M2 — Admin Settings UI: Modes config subtab (missing UI)

```md
Task: Add Admin-only "Modes" configuration surface in Settings.

Placement:
- Add as a subtab under Agent Configuration OR dedicated Settings tab "Modes".

Requirements:
1) Admin-only list of system modes (fixed, non-removable):
   - Orchestrator
   - Planner
   - Architect
   - Deep Research
   - Code
2) For each mode show:
   - system-owned badge (immutable)
   - editable "Mode System Instructions" textarea
   - read-only capability summary (e.g., can spawn subagents, tool access type)
3) Add save/reset controls with dirty-state protection.
4) Show last edited by + last edited at metadata.
5) Add version history drawer for instruction changes (at least latest N revisions).

Files likely:
- frontend/src/components/settings/SettingsPage.tsx
- frontend/src/components/settings/AgentTab.tsx
- frontend/src/components/settings/ModesTab.tsx (new)
- backend admin routes/services for mode instruction CRUD

Acceptance:
- Only admin roles can access this subtab.
- Non-admin sees no edit surface.
- Admin edits persist and apply to subsequent sessions.
```

---

## Prompt M3 — Runtime execution policy by mode (close backend gap)

```md
Task: Complete runtime mode enforcement so frontend picker cannot bypass policy.

Policy rules:
1) orchestrator:
   - can route tasks to other modes,
   - should not directly run high-risk execution tools unless explicitly policy-allowed.
2) planner/architect/deep_research:
   - read-only tool profile (search/retrieve/summarize/plan), no destructive execution.
3) code:
   - only mode allowed to run execution tools and spawn subagents.

Requirements:
1) Enforce policy at tool-selection layer server-side.
2) Validate requested mode per turn against server policy.
3) If model emits disallowed tools:
   - block execution,
   - return structured refusal + suggested allowed route.
4) Add mode-to-capability matrix in one central module.

Files likely:
- backend/modes.py
- universal_navigator.py
- main.py (session config ingress)

Acceptance:
- Disallowed tool calls are blocked regardless of client payload.
- Code mode can execute/spawn; other modes cannot.
- Orchestrator can route but obeys execution limits.
```

---

## Prompt M4 — Orchestrator routing workflow (node-level delegation)

```md
Task: Implement orchestrator mode as the only router to specialist modes.

Requirements:
1) In orchestrator mode:
   - classify user intent,
   - select target mode (planner/architect/deep_research/code),
   - delegate subtask with context envelope,
   - gather result and produce final synthesis.
2) Maintain traceability:
   - include route decision logs,
   - include child-mode result references in final answer.
3) Prevent direct user-forced bypass of routing constraints.
4) Add timeout/fallback behavior if delegated mode fails.

Acceptance:
- Research tasks route to deep_research.
- Build/implementation tasks route to code.
- Final answer returns through orchestrator with summarized output.
```

---

## Prompt M5 — Integration parity: `/mode` UX + inline picker (Telegram + others)

```md
Task: Ensure mode selection parity across frontend and integrations.

Requirements:
1) Frontend:
   - mode picker remains visible in composer where applicable,
   - current mode badge shown in conversation header/status.
2) Telegram:
   - `/mode` command opens inline keyboard selector,
   - selection persists per session/user,
   - command `/mode` with no args shows current mode + options.
3) Slack/Discord parity (if supported in project scope):
   - slash or command equivalent for mode get/set.
4) All integrations must use same backend mode validation endpoint.

Files likely:
- main.py
- integrations/telegram.py
- integrations/slack_connector.py
- integrations/discord.py
- frontend components/hooks for mode display

Acceptance:
- Mode changes from any channel reflect in runtime policy immediately.
- Invalid mode names are rejected with helpful guidance.
```

---

## Prompt M6 — Industry-standard feasibility + guardrails (implementation checklist)

```md
Task: Add a standards-aligned checklist and enforceable controls for Modes rollout.

Industry alignment goals:
1) Least privilege + deny by default for tool access.
2) Server-side authorization as source of truth.
3) Structured tool-call contracts and strict validation.
4) Full auditability of admin policy/instruction changes.

Implementation checklist:
- Deny-by-default mode capability matrix.
- RBAC on all admin mode config endpoints.
- Structured schema validation for mode payloads/tool calls.
- Audit log entries for:
  - mode changes,
  - blocked tool attempts,
  - orchestrator route decisions.
- Regression tests for mode bypass attempts.

Acceptance:
- Security tests prove non-admin cannot mutate mode instructions.
- Bypass attempts via crafted ws payload fail.
- Audit records exist for all critical policy actions.
```

---

## Master execution prompt (M1→M6)

```md
Implement prompts M1 through M6 from docs/modes-system-node-prompts.md in strict order.
Do not proceed to next prompt until acceptance criteria of current prompt pass.
After each prompt, output:
1) changed files,
2) commands run and results,
3) acceptance checklist pass/fail,
4) unresolved risks.
```
