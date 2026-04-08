# Aegis Modes — Industry Standards & Feasibility Brief (April 2026)

## Goal
Define a robust **mode system** where each mode behaves like an admin-controlled system subagent:

- Orchestrator
- Planner
- Architect
- Deep Research
- Code

These modes inherit global system policy and mode-specific instructions, while remaining immutable for end users.

## Industry patterns we should mirror

### 1) Hierarchical instruction priority
Modern agent stacks treat top-level system policy as authoritative and non-overridable by user turns.

Why this matters for Aegis modes:
- Mode definitions should sit above user messages.
- Admin policy + mode policy should be merged as system context before runtime user prompts.

### 2) Supervisor/worker (router + specialist) architecture
Leading multi-agent implementations use a router/supervisor agent that delegates to specialist workers and synthesizes outputs.

Why this matters for Aegis modes:
- Orchestrator mode should be the only router.
- Specialist modes should return structured outputs that Orchestrator composes.

### 3) Tool access via least privilege
Best-in-class agent systems gate tools per context, with strict allow/deny policies and explicit high-risk approval.

Why this matters for Aegis modes:
- Read-only modes (Planner/Architect/Deep Research) should not execute mutating tools.
- Code mode should be the only mode that can execute code and spawn subagents.

### 4) Chat-platform UX for mode switching
For Telegram, command + inline keyboard callback UX is the standard low-friction interaction for bot configuration controls.

Why this matters for Aegis modes:
- `/mode` command should display current mode and (next iteration) present inline options.
- Selection should update per-user runtime mode server-side.

## Feasibility in current Aegis codebase

### Already feasible now
- Session-scoped settings are already propagated over WebSocket config payloads.
- System prompt composition already supports authoritative global instructions.
- Tool manifests already support dynamic filtering via runtime settings.
- Telegram slash command handling already exists (`/model`, `/stream`, `/reason`, etc.).

### Implemented in this pass
1. Added a frontend mode picker in the input bar.
2. Added session setting propagation for `agent_mode`.
3. Added backend mode policy helpers and tool-blocking by mode.
4. Added `/mode` slash command support in Telegram command handling.
5. Added tests for mode normalization, tool gating, and `/mode` command behavior.

### Next step (recommended)
Add admin-managed mode instruction templates in Admin → Agent settings:
- Global system instruction (existing)
- Mode instruction blocks (new): orchestrator/planner/architect/deep_research/code
- Storage in platform settings table
- Read path merged into runtime prompt as:
  1. Global policy
  2. Mode policy
  3. Runtime user instruction (lowest)

## Proposed mode contract (v1)

### Orchestrator
- Purpose: classification + delegation + synthesis
- Tools: read-only/meta only (no subagent spawn direct tool call)
- Output: delegated plan + final synthesis

### Planner
- Purpose: task decomposition, milestones, risk checks
- Tools: none (or minimal read-only context access)
- Output: numbered plan with assumptions

### Architect
- Purpose: system design, tradeoff analysis
- Tools: none (or minimal read-only context access)
- Output: architecture proposal + alternatives + rationale

### Deep Research
- Purpose: evidence-first analysis and synthesis
- Tools: none in strict mode (or controlled retrieval only in future)
- Output: findings, confidence, open questions, citations (when available)

### Code
- Purpose: implementation and execution
- Tools: full execution set
- Special capability: only mode allowed to spawn subagents

## External references
- OpenAI instruction hierarchy and system-role precedence work:
  - https://cdn.openai.com/pdf/14e541fa-7e48-4d79-9cbf-61c3cde3e263/ih-challenge-paper.pdf
- Anthropic agent architecture patterns (supervisor/specialist):
  - https://resources.anthropic.com/hubfs/Building%20Effective%20AI%20Agents-%20Architecture%20Patterns%20and%20Implementation%20Frameworks.pdf
- Anthropic safety/system-card coverage of prompt injection and tool misuse risks:
  - https://www-cdn.anthropic.com/07b2a3f9902ee19fe39a36ca638e5ae987bc64dd.pdf
- Telegram bot inline keyboard + callback UX pattern:
  - https://core.telegram.org/bots/2-0-intro
