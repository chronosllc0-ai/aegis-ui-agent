# Skills D/E/F.1 — Copy-Paste Implementation Prompts (Repo-Tailored)

These are implementation-grade prompts tailored to this repository’s current structure.

---

## Prompt D.1 — Skills tab UI + Admin subtab (repo-specific)

```md
Task: Implement Skills management UI in existing Settings architecture.

Use current settings surfaces:
- frontend/src/components/settings/SettingsPage.tsx
- frontend/src/components/settings/AgentTab.tsx
- frontend/src/components/settings/ToolsTab.tsx
- frontend/src/context/useSettingsContext.tsx
- frontend/src/hooks/useSettings.ts
- frontend/src/lib/api.ts

Implementation requirements:
1) Add a new Settings tab label: "Skills" in `SettingsPage.tsx`.
2) Create `frontend/src/components/settings/SkillsTab.tsx` with two panes:
   - User pane (always visible):
     - installed skills list,
     - enable/disable toggle,
     - delete/uninstall action,
     - metadata chips (version/source/updated_at/risk tag).
   - Admin pane (visible only for admin/superadmin):
     - org allow/block policy toggles,
     - require-approval-before-install switch,
     - org default-enabled skill set.
3) Add `frontend/src/hooks/useSkills.ts` for data fetching/mutations (marketplace installed/toggle/delete/policy).
4) Wire role awareness from existing `authUser.role` patterns already used in `App.tsx` and admin components.
5) Ensure optimistic toggles with rollback and toasts on failures.
6) Keep runtime settings payload backward-compatible (do not break existing wsConfig shape).

Backend/API alignment:
- Add routes under `main.py` (or a dedicated backend router if preferred) for:
  - GET /api/skills/installed
  - POST /api/skills/toggle
  - DELETE /api/skills/{skill_id}
  - GET/POST admin policy endpoints under /api/admin/skills/*

Acceptance:
- Skills tab appears in settings.
- Non-admin users cannot access admin pane controls.
- Toggle/delete works and persists after refresh.
- `cd frontend && npm run build` succeeds.
```

### Admin UI subtab spec (explicit)

Use this exact layout inside `SkillsTab.tsx`:

1) Subtab header (segment control):
   - `My Skills` (all users)
   - `Admin Controls` (admin/superadmin only)
2) `Admin Controls` sections:
   - **Policy Defaults**
     - Toggle: `Require approval before install`
     - Multi-select: `Default enabled skills for new users`
   - **Allow/Block List**
     - Search input
     - Table columns: Skill, Version, Risk, Allowed, Blocked, Updated
     - Row actions: Allow / Block / Reset
   - **Org Install Audit**
     - Filters: user, skill, date range, action
     - Read-only timeline with pagination
3) Confirmation UX:
   - Blocking a skill => confirm modal with impact copy
   - Reset policy => confirm modal
4) Permissions:
   - Hide entire `Admin Controls` subtab for non-admin users
   - Server must still enforce RBAC for every admin endpoint

Done criteria for Admin subtab:
- Subtab is visible only for admin roles.
- Policy changes persist and reload correctly.
- Blocked skills are prevented in user install flow.
- Admin audit list loads and paginates without UI errors.

---

## Prompt E.1 — Hub submission/review states (repo-specific)

```md
Task: Add Skill Hub submission + review workflow states with deterministic transitions.

Recommended module placement:
- backend/tasks/ or new backend/skills_hub/ package (preferred)
- route entry in `main.py` or dedicated router similar to:
  - backend/gallery/router.py
  - backend/connectors/router.py

State machine:
- draft -> submitted -> under_review -> (changes_requested -> submitted) OR approved -> published
- from published: suspended or archived
- rejected terminal unless resubmission creates new revision

Backend requirements:
1) Create models/schemas for submission + review action payloads.
2) Implement transition validator function (`allowed_transitions(current_state)` pattern).
3) Persist reviewer notes and transition history (audit trail).
4) Add endpoints:
   - POST /api/skills/hub/submissions
   - GET /api/skills/hub/submissions/{id}
   - POST /api/skills/hub/submissions/{id}/transition
   - GET /api/skills/hub/review-queue (admin)

Frontend requirements:
1) Add `frontend/src/components/skills-hub/` with:
   - `SubmissionForm.tsx`
   - `SubmissionStatusTimeline.tsx`
   - `ReviewQueue.tsx` (admin)
2) Add "Submit to Hub" action from Skills tab item rows.
3) Show exact status badges and reviewer notes history.
4) Disable impossible actions client-side, but enforce server-side regardless.

Tests:
- Add `tests/test_skills_hub_states.py` for legal/illegal transitions.
- Add `tests/test_skills_hub_permissions.py` for role checks.

Acceptance:
- Transition matrix enforced server-side.
- Admin review queue works with filters (state/date/risk if available).
- Published state controls marketplace visibility.
```

---

## Prompt F.1 — VirusTotal scan integration + risk tags (repo-specific)

```md
Task: Integrate VirusTotal scanning into skill submission/install pipelines and expose risk tags across UI.

Backend integration points:
- config.py (new VT settings)
- main.py (submission/install endpoints)
- new module: backend/security/virustotal.py
- skills install/hub services created in D.1/E.1

Config requirements:
1) Add env vars in config settings:
   - VIRUSTOTAL_API_KEY
   - VIRUSTOTAL_TIMEOUT_SECONDS (default)
   - VIRUSTOTAL_ENABLED (bool)
2) Add placeholders to `.env.example` only (no secrets).

Service requirements (`backend/security/virustotal.py`):
1) `submit_file_for_scan(...)`
2) `fetch_scan_report(...)`
3) `map_report_to_risk_tag(...)` returning one of:
   - clean, low_risk, suspicious, malicious, scan_pending, scan_failed

Policy gating:
1) Block install/publish when tag = malicious.
2) Require explicit admin override when tag = suspicious.
3) Allow clean/low_risk by default.
4) If scan_pending/scan_failed, show warning and configurable policy fallback.

Frontend display requirements:
- Show risk tags in:
  - `SkillsTab.tsx` installed list
  - `skills-hub/ReviewQueue.tsx`
  - marketplace cards/detail (from existing or new marketplace component)
- Add filter chips for risk tags in admin review UI.

Tests:
- `tests/test_virustotal_risk_mapping.py` for mapping logic.
- `tests/test_skills_install_policy.py` for gate enforcement.
- frontend tests for badge rendering and blocked install UX.

Acceptance:
- All skill artifacts receive scan status.
- Risk tags visible in all target UIs.
- Policy enforcement blocks/overrides correctly.
- No secret leakage in logs/responses.
```

---

## Master execution prompt (D.1 → E.1 → F.1)

```md
Implement D.1, then E.1, then F.1 from docs/skills-prompts-def-implementation.md.
Do not skip acceptance checks.
After each stage:
1) list changed files,
2) list commands and outputs,
3) report acceptance criteria pass/fail,
4) stop and remediate on any failure.
```
