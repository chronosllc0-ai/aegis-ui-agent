# Public Site, Auth Slider, And Shared Docs Design

## Summary

This spec defines the next public-facing Aegis experience:

- a story-led landing page with a richer header, footer, and alternating product-story modules
- a redesigned auth page with a persistent side slider that combines product proof and setup guidance
- embedded docs inside the main frontend app
- a true standalone docs experience backed by the same shared docs content source

Pricing is explicitly out of scope for this pass and will be added later.

## Goals

- Make the public product surface feel intentional, modern, and launch-ready.
- Add a side slider to both the landing page and auth page.
- Expand the landing page into a full public site instead of a single hero and a few basic sections.
- Create a real docs portal with API reference, tutorials, FAQ, and changelog.
- Keep the main app domain as the canonical entry point while also providing a true standalone docs experience.
- Ensure both docs surfaces stay synchronized through one shared content system.

## Approved Product Direction

### Overall visual direction

- Direction: Story-Led Launch
- Homepage structure: Alternating story modules
- Auth slider role: Hybrid product proof plus setup guidance
- Canonical public entry point: Main app domain
- Docs architecture: Shared docs content rendered in both embedded and standalone docs surfaces
- Standalone docs: True standalone experience, not just a themed route in the main app

## Information Architecture

### Main app domain

The main frontend remains the canonical public entry point and should own:

- `/` for the story-led landing page
- `/auth` for public auth
- `/docs/*` for embedded docs inside the main app shell
- the existing signed-in product experience

### Standalone docs domain

The standalone docs frontend should be deployable as its own app, ideally at `docs.<domain>`, and should own:

- docs homepage
- docs section navigation
- API reference browsing
- tutorials
- FAQ
- changelog

### Interconnection rules

- Main app header links directly to docs entry points.
- Landing page sections link to relevant docs pages where explanation depth is needed.
- Auth page links to setup-oriented docs pages.
- Embedded docs link to the standalone docs portal for full browsing.
- Standalone docs link back to product home and auth.
- Shared slugs and shared content metadata keep both docs surfaces aligned.

## Architecture

## Main frontend app

The existing `frontend/` app remains the product shell and public entry point. It gains:

- public route handling for landing, auth, and embedded docs
- a richer public-site header and footer
- public docs views under `/docs/*`
- the current signed-in operator experience without regression

## Standalone docs app

A second frontend app should be introduced for the standalone docs experience. It should:

- have a docs-first layout and navigation system
- render the same shared docs content as the embedded docs routes
- feel like a complete docs portal rather than a reused marketing page

## Shared docs system

Two shared units should sit above the two frontends:

- `shared/docs/`
  Typed docs content and metadata
- `shared/docs-ui/`
  Shared article rendering primitives and docs layout helpers that can be reused by both frontends

This avoids duplicated copy, duplicated slugs, and divergent docs behavior across the embedded and standalone docs surfaces.

## Routing Model

The public-facing routes should become explicit rather than being driven only by local UI state.

Recommended route model:

- `/` -> landing page
- `/auth` -> auth page
- `/docs` -> embedded docs home
- `/docs/:section/:slug` or comparable nested structure -> embedded doc pages
- signed-in app routes remain available after auth

The standalone docs app should mirror docs slugs with its own routing model so the same document identifiers exist in both places.

## Landing Page Design

The landing page should evolve from a standard hero page into a story-led launch surface built from alternating modules.

### Header

The header should become comprehensive and usable as a real public navigation surface.

Required links:

- Product
- Docs
- Tutorials
- API
- FAQ
- Changelog
- Sign in
- Get started

The docs link should be prominent because the docs portal is a first-class part of the product surface, not an afterthought.

### Hero

The hero should keep a strong product message while incorporating a side slider.

Hero content should include:

- a concise statement of what Aegis does
- a short narrative explaining vision-first UI navigation
- a primary CTA to get started
- a secondary CTA to read docs
- a side slider that communicates proof, motion, and product context

### Side slider on landing

The landing slider should support the story-led launch tone while staying technically credible.

Suggested slide themes:

- session view and live control
- screenshot analysis and UI understanding
- live steering and transcripts
- docs/tutorial jump points for deeper reading

The slider should feel like a living product surface, not a decorative carousel.

### Alternating story modules

The landing page body should be restructured as alternating modules instead of a uniform grid of sections.

Suggested modules:

- why vision-first navigation matters
- how live steering and voice control work
- integrations and workflow examples
- operational credibility and deployment story
- docs gateway with direct links to quickstart, API reference, tutorials, FAQ, and changelog

Docs links should appear contextually inside these sections wherever the user would reasonably need more depth.

### Footer

The footer should become a second navigation system, not a single-line closing element.

Footer groups should include:

- product
- docs
- developer resources
- tutorials
- changelog
- auth entry points

## Auth Page Design

The auth page should become a guided entry point into the product instead of an isolated form card.

### Layout

- desktop: two-column layout
- mobile: stacked layout with auth first and slider second

### Auth column

The auth column keeps:

- sign in / sign up switch
- SSO options
- email/password flows
- trust copy
- back-to-home navigation

### Auth slider

The auth slider should serve a hybrid role: product proof plus setup guidance.

Suggested slide themes:

- what happens after sign-in
- how to connect providers or API keys
- how to start the first live session
- where tutorials and docs live

This should reduce onboarding friction and give first-time users a clearer path after authentication.

### Docs links on auth

The auth page should link to:

- quickstart
- auth setup
- provider keys / BYOK
- deployment guidance

These links should be present inline, not only in the global header.

## Shared Docs Content Model

The docs system should use one shared, typed content source.

### Content types

Day-one content types:

- doc pages
- API reference entries
- tutorials
- FAQ entries
- changelog entries

### Shared metadata

Every doc-like entry should expose typed metadata such as:

- slug
- title
- summary
- category
- order
- audience
- updatedAt
- related links

### Day-one docs information architecture

Minimum docs sections for launch:

- Quickstart
- Authentication
- Provider keys / BYOK
- Live sessions
- Voice and transcripts
- Integrations
- Workflow templates
- Deployment
- API reference
- Tutorials
- FAQ
- Changelog

## Embedded Docs Experience

The embedded docs experience should live in the main frontend app under `/docs/*`.

Purpose:

- serve users who discover docs from landing, auth, or in-product links
- keep product context while still providing structured documentation
- offer the same core content as the standalone docs app

Embedded docs should reuse shared docs rendering primitives while staying visually compatible with the main product shell.

## Standalone Docs Experience

The standalone docs app should have its own docs-first shell.

Required characteristics:

- separate frontend app and deploy target
- docs homepage
- left-side navigation
- top utility navigation
- article layout
- API reference browsing
- tutorial browsing
- FAQ and changelog pages

This experience should feel purpose-built for reading and reference, not like a marketing page wearing a docs skin.

## Shared Rendering Primitives

To avoid drift, both docs surfaces should reuse shared rendering primitives for:

- article header
- section anchors
- related docs
- callouts
- code blocks
- prev/next navigation
- docs metadata presentation

This logic belongs in shared UI code rather than being copied into both frontends.

## Implementation Boundaries

Recommended boundaries:

- `frontend/src/components/`
  Expanded public-facing UI components including landing sections and auth layout improvements
- `frontend/src/public/` or equivalent
  Public docs route components and helpers
- `frontend/src/router/` or equivalent
  Public route handling for landing, auth, and docs
- `docs-site/`
  Standalone docs frontend app
- `shared/docs/`
  Shared docs content source
- `shared/docs-ui/`
  Shared docs rendering primitives

Important boundary rules:

- keep docs content out of page shells
- keep slider content definitions separate from the generic slider component
- keep signed-in app behavior isolated from public-site routing changes
- avoid duplicating article-rendering logic across the two docs surfaces

## Validation

The implementation plan derived from this spec should include validation for:

- main frontend build passes
- standalone docs app build passes
- signed-in app shell still works
- auth flow still works
- embedded docs routes resolve correctly
- shared docs content renders correctly in both docs surfaces
- header/footer/docs links resolve correctly
- landing, auth, and docs layouts behave correctly on mobile and desktop

## Risks

Primary implementation risks:

- introducing public routing without regressing the signed-in app flow
- creating a second frontend without duplicating docs rendering logic
- keeping the public product shell distinct from the signed-in operator shell

## Out Of Scope For This Pass

- pricing implementation
- unrelated signed-in app redesign
- non-docs CMS or external authoring system
- speculative features not requested by the user
