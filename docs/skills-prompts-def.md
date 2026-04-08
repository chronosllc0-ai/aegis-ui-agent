# Skills Prompt D/E/F Pack

These prompts continue the Skills roadmap and are focused on:
- **Prompt D:** Skills tab UI + admin subtab
- **Prompt E:** Hub submission/review lifecycle states
- **Prompt F:** VirusTotal integration + runtime risk tags

Use them in order and enforce acceptance checks before moving forward.

---

## Prompt D — Skills tab UI + admin subtab

```md
Task: Implement first-class Skills UI in Settings for both user and admin experiences.

Scope:
1) Add a dedicated "Skills" settings tab for all users.
2) Add an "Admin" subtab/section inside Skills for admin-only policy controls.

User-side requirements:
- Installed skills list with:
  - enable/disable toggle,
  - uninstall/delete action,
  - version + source + last updated metadata,
  - badges (enabled/disabled/update available/risk level).
- Marketplace shortcut CTA from Skills tab.
- Empty state with guided install action.

Admin-subtab requirements:
- Org policy controls:
  - allow/block specific skills,
  - require approval before user install,
  - set default enabled skills for new users.
- Moderation view of installed skills by org/user (search + filters).
- Destructive actions require confirmation modal + audit event.

Technical requirements:
- Role-based rendering/route guards for admin-only controls.
- Optimistic toggle UX with rollback on API failure.
- Shared query/mutation hooks for skills operations.
- No duplicated state sources (single canonical skills store in frontend).

Likely files:
- frontend/src/components/settings/SettingsPage.tsx
- frontend/src/components/settings/SkillsTab.tsx (new)
- frontend/src/components/settings/SkillsAdminSubtab.tsx (new)
- frontend/src/hooks/useSkills.ts (new or extend)
- frontend/src/context/useSettingsContext.tsx (if runtime payload wiring needed)

Acceptance criteria:
- Non-admin users see Skills tab but no admin controls.
- Admin users can manage policy + org-level actions.
- User toggles and deletes persist correctly after reload.
- Build/test pass with no TypeScript regression.
```

---

## Prompt E — Hub submission/review states

```md
Task: Implement Skill Hub submission + review workflow states end-to-end.

State model:
- draft
- submitted
- under_review
- changes_requested
- approved
- rejected
- published
- suspended
- archived

Requirements:
1) Backend workflow:
   - Create submission endpoint.
   - Transition endpoints with guardrails (only legal transitions).
   - Reviewer notes + changelog capture.
   - Immutable audit log per transition.
2) User/creator UI:
   - "Submit skill" form (metadata, docs, permissions, package reference).
   - Submission status timeline UI.
   - "Address changes" flow that resubmits from `changes_requested`.
3) Admin/reviewer UI:
   - Review queue with filters by state/risk/date.
   - Approve/reject/request-changes actions with mandatory rationale.
   - Publish/unpublish/suspend controls for post-approval governance.
4) Notifications:
   - creator notified on each state transition,
   - reviewer assignment/change notifications.

Data/UX constraints:
- State transitions must be deterministic and server-validated.
- UI must never show impossible transitions.
- Preserve reviewer comments history.

Likely files:
- backend/skills_hub/*.py (new workflow handlers)
- main.py (route wiring)
- frontend/src/components/skills-hub/* (new)
- frontend/src/lib/api/*skillsHub*

Acceptance criteria:
- Full transition matrix covered by tests.
- Creator and reviewer UIs reflect exact current state.
- Audit trail available for every transition.
- Published skills appear in marketplace only when state is `published`.
```

---

## Prompt F — VirusTotal scan integration + risk tags

```md
Task: Integrate VirusTotal scans into skill ingestion/review pipeline and expose risk tags in UI.

Requirements:
1) Backend integration:
   - Add scanning service wrapper for VirusTotal API.
   - Scan artifacts at submission/install/update points.
   - Persist scan results (scan_id, verdict, detection ratio, timestamp, raw reference URL).
2) Risk model/tagging:
   - Define normalized risk tags, e.g.:
     - clean
     - low_risk
     - suspicious
     - malicious
     - scan_failed
     - scan_pending
   - Map VirusTotal verdicts/signals into internal tags deterministically.
3) Policy enforcement:
   - Block install for `malicious` by default.
   - Warn + require explicit admin override for `suspicious`.
   - Allow normal flow for `clean` / `low_risk`.
4) UI surfaces:
   - Show risk tag badge in marketplace cards, skill detail, installed list, and review queue.
   - Display latest scan timestamp + quick link to scan report where policy allows.
   - Add filter chips for risk tags in admin review queue.
5) Operational safety:
   - Timeout/retry strategy for scan API.
   - Graceful fallback state (`scan_pending`/`scan_failed`) with clear messaging.
   - Do not expose API key/secrets in logs or frontend payloads.

Testing requirements:
- Unit tests for VT -> risk-tag mapping.
- Integration tests for install/submit policy gates by tag.
- UI tests for badge rendering and blocked install flows.

Likely files:
- src/utils/config.py (VT keys/settings)
- backend/security/virustotal.py (new)
- backend/skills_hub/* and install handlers
- frontend skills marketplace/installed/admin components

Acceptance criteria:
- Every submission/install path has scan status.
- Risk tags are visible and actionable in all relevant UIs.
- Policy gates enforce malicious/suspicious behavior correctly.
- Tests pass; no secret leakage.
```

---

## Combined execution prompt (D+E+F)

```md
Implement Prompt D, then E, then F from docs/skills-prompts-def.md in strict sequence.
Do not proceed if acceptance criteria of the current prompt fail.
For each prompt provide:
1) changed files,
2) commands run,
3) acceptance checklist results,
4) follow-up risks.
```
