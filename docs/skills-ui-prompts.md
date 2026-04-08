# Skills UI Prompt Pack (Admin + User + Marketplace)

This pack is specifically for the Skills feature you asked about:
- **Admin side:** settings area (Agent Config subtab or dedicated Skills subtab)
- **User side:** enable/disable installed skills, delete installed skills
- **Marketplace:** browse/install/update skills from a curated source

Run prompts in order and do not skip acceptance checks.

---

## Prompt 1 — Data model + API contract for skills lifecycle

```md
Task: Implement/verify backend API contract for full skills lifecycle used by admin/user/marketplace UIs.

Requirements:
1) Add/verify entities:
   - SkillCatalogItem (marketplace metadata)
   - InstalledSkill (tenant/user scoped install record)
   - SkillToggleState (enabled/disabled)
2) Add/verify endpoints:
   - GET /api/skills/marketplace
   - GET /api/skills/installed
   - POST /api/skills/install
   - POST /api/skills/toggle
   - DELETE /api/skills/{skill_id}
   - POST /api/skills/update (optional, if versioned updates supported)
3) Enforce auth/role boundaries:
   - Admin-only endpoints for org-wide policy where applicable
   - User endpoints for personal install/toggle/delete
4) Return normalized response envelope:
   - { ok, data, error, metadata }

Acceptance:
- OpenAPI/docs reflect all routes.
- Permission checks verified in tests.
- No secret/token exposure in responses.
```

---

## Prompt 2 — Admin UI (Settings: Agent Config subtab OR dedicated Skills subtab)

```md
Task: Add Skills Management UI in admin settings surface.

Requirements:
1) Place UI either:
   - inside Agent Configuration as a "Skills" section, OR
   - as a new Settings tab "Skills" (preferred if feature is large)
2) Admin controls:
   - view installed skills across scope
   - enable/disable policy defaults
   - remove installed skill from org scope
   - optional: pin/feature skills for end users
3) Add clear status badges:
   - installed, enabled, disabled, update available
4) Add confirmation modals for destructive actions (delete/uninstall).
5) Wire to backend endpoints from Prompt 1.

Files likely:
- frontend/src/components/settings/SettingsPage.tsx
- frontend/src/components/settings/* (new Skills tab component)
- frontend/src/hooks/* (skills query/mutation hooks)

Acceptance:
- Admin can toggle/delete skills from settings.
- Role-restricted UI hidden/disabled for non-admin users.
- Loading/error/success states are complete.
```

---

## Prompt 3 — User Skills Manager UI (toggle on/off + delete downloaded skills)

```md
Task: Implement end-user Skills manager for installed/downloaded skills.

Requirements:
1) Add user-accessible Skills screen/section showing installed skills list.
2) Per skill actions:
   - Toggle enabled/disabled
   - Delete/uninstall downloaded skill
3) Show source/version metadata and last-updated timestamp.
4) Add optimistic UI updates with rollback on failure.
5) Persist toggle state and reflect immediately in agent runtime config payload.

Files likely:
- frontend/src/components/settings/*Skills*.tsx
- frontend/src/hooks/useSettings.ts (or dedicated useSkills)
- frontend/src/context/useSettingsContext.tsx (if runtime config includes enabled skills)

Acceptance:
- User can toggle a skill and see immediate state change.
- User can delete installed skill with confirmation.
- Runtime payload includes enabled skills only.
```

---

## Prompt 4 — Marketplace UI (discover/install/update)

```md
Task: Build Skills Marketplace UI where users/admins can discover and install skills.

Requirements:
1) Marketplace list/grid with:
   - name, description, author/publisher, version, rating/downloads (if available)
   - tags/categories and search/filter
2) Skill detail drawer/page:
   - changelog, permissions required, compatibility notes
3) Install flow:
   - install button
   - conflict/duplicate handling
   - post-install state updates to installed list
4) Update flow (if versions available):
   - show "update available"
   - one-click update
5) Safety UX:
   - permission disclosure before install
   - source trust indicator (verified/unverified)

Files likely:
- frontend/src/components/marketplace/*
- frontend/src/lib/api skills client
- backend marketplace proxy/service routes

Acceptance:
- User can browse, install, and see installed state reflected in user skills manager.
- Search/filter works.
- Install failures handled with clear error messaging.
```

---

## Prompt 5 — Runtime integration (enabled skills actually affect agent tool availability)

```md
Task: Wire enabled skills into runtime/tool availability so toggles have real effect.

Requirements:
1) At session start and on config updates, resolve enabled installed skills.
2) Merge skill-provided capabilities/tools into allowed runtime surface.
3) Respect mode-based/tool policy gating (agent mode restrictions still apply).
4) Ensure disabled/deleted skills are excluded from runtime immediately.

Files likely:
- backend/modes.py
- universal_navigator.py
- main.py websocket config handling
- frontend settings/wsConfig plumbing

Acceptance:
- Enabling a skill makes its capability available.
- Disabling/deleting removes capability without restart (or with documented refresh behavior).
- No bypass of existing safety/tool-policy constraints.
```

---

## Prompt 6 — QA, tests, and migration/rollout

```md
Task: Add full regression coverage and rollout checklist for Skills UI + API.

Required tests:
1) API tests:
   - marketplace fetch, install, toggle, delete, update
   - auth/role boundary coverage
2) Frontend tests:
   - admin skill controls render and mutate correctly
   - user toggle/delete flows
   - marketplace install flow + error handling
3) Runtime tests:
   - enabled skills reflected in session tool availability
   - disabled skills excluded
4) E2E smoke:
   - install from marketplace -> appears in installed list -> enable -> usable -> disable/delete -> unavailable

Acceptance:
- Tests pass in CI.
- No TypeScript build regressions.
- ONBOARDING + docs updated with operations/permissions notes.
```

---

## One-shot execution prompt (if you want full implementation in one run)

```md
Implement Prompts 1–6 from docs/skills-ui-prompts.md in strict order without skipping acceptance checks.
After each prompt:
1) list changed files,
2) list commands run and results,
3) stop on failure and provide remediation before continuing.

At the end provide:
- architecture summary,
- admin UX summary,
- user UX summary,
- marketplace UX summary,
- test matrix,
- residual risks.
```
