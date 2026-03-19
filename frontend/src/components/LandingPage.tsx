import { EntrySlider, type EntrySlide } from './EntrySlider'
import { Icons } from './icons'
import { PROVIDERS, renderProviderIcon } from '../lib/models'
import { PublicFooter } from '../public/PublicFooter'
import { PublicHeader } from '../public/PublicHeader'

type LandingPageProps = {
  onGetStarted: () => void
  onOpenDocsHome: () => void
  onOpenDoc: (slug: string) => void
  docsPortalHref: string
}

const FEATURES = [
  {
    title: 'Vision-first navigation',
    description: 'Aegis reasons over the live screen state before every major action so the operator stays aligned with what is actually visible.',
    icon: Icons.globe,
  },
  {
    title: 'Real-time control',
    description: 'Steer, interrupt, queue, and monitor transcripts without restarting the session or losing context.',
    icon: Icons.workflows,
  },
  {
    title: 'Live voice loop',
    description: 'Voice input, transcripts, and action logs flow through the same operator surface for fast handoffs.',
    icon: Icons.mic,
  },
  {
    title: 'Bring your own keys',
    description: 'Use your own provider accounts across Gemini, OpenAI, Anthropic, Mistral, and Groq from one settings surface.',
    icon: Icons.settings,
  },
  {
    title: 'Docs-driven onboarding',
    description: 'Quickstart, API reference, tutorials, FAQ, and changelog are wired directly into the public product story.',
    icon: Icons.check,
  },
  {
    title: 'Deploy-ready stack',
    description: 'FastAPI, WebSockets, Playwright, PostgreSQL, Docker, and Railway-friendly deployment paths are already in the repo.',
    icon: Icons.menu,
  },
]

const STEPS = [
  {
    title: 'Capture',
    text: 'Grab the current viewport so the agent reasons over the real screen instead of guessing from stale state.',
  },
  {
    title: 'Analyze',
    text: 'Use multimodal reasoning to understand layout, intent, and the interactive elements available right now.',
  },
  {
    title: 'Act',
    text: 'Execute clicks, typing, scrolling, and navigation while the operator can still steer the task.',
  },
  {
    title: 'Report',
    text: 'Stream frames, workflow steps, logs, and transcripts back into the shell so progress stays legible.',
  },
]

const PRICING = [
  {
    name: 'Free',
    price: '$0',
    period: '/month',
    description: 'Run live sessions with your own provider keys.',
    cta: 'Start free',
    features: ['Unlimited BYOK sessions', 'All providers supported', 'Embedded docs access', 'Self-hosted path'],
    highlight: false,
  },
  {
    name: 'Pro',
    price: '$29',
    period: '/month',
    description: 'For operators who want credits, saved workflows, and faster setup.',
    cta: 'Start Pro trial',
    features: ['Everything in Free', 'Included usage credits', 'Workflow templates', 'Priority support'],
    highlight: true,
  },
  {
    name: 'Team',
    price: '$79',
    period: '/seat/month',
    description: 'Shared operations, SSO, and team-level workflow management.',
    cta: 'Talk to us',
    features: ['Everything in Pro', 'Shared key pools', 'Team workflow library', 'SSO and admin support'],
    highlight: false,
  },
]

const LANDING_SLIDES: EntrySlide[] = [
  {
    id: 'operator-loop',
    eyebrow: 'Operator loop',
    title: 'The screen is the source of truth.',
    description:
      'Aegis captures the viewport, reasons over the live UI state, and acts with the context of what is actually visible right now.',
    bullets: [
      'Vision-first navigation that adapts to changing layouts',
      'Live frame updates while the session is running',
      'Built for real operator supervision instead of blind automation',
    ],
    statLabel: 'Live cycle',
    statValue: 'See -> Reason -> Act',
    icon: (className) => Icons.globe({ className }),
  },
  {
    id: 'steer-and-voice',
    eyebrow: 'Real-time control',
    title: 'Interrupt, steer, queue, and speak without restarting.',
    description:
      'Aegis keeps the operator in the loop. You can redirect a task mid-run, push voice input, or queue the next move while the current one is still executing.',
    bullets: [
      'Steer or interrupt without losing session state',
      'Transcript display and voice-friendly flows',
      'Action logs and workflow view stay in sync with the run',
    ],
    statLabel: 'Control',
    statValue: 'Text + Voice',
    icon: (className) => Icons.mic({ className }),
  },
  {
    id: 'docs-and-deploy',
    eyebrow: 'Build and deploy',
    title: 'Read the docs, bring your own keys, and ship fast.',
    description:
      'The public site, auth flow, embedded docs, and standalone docs portal are designed to carry a user all the way from discovery to a live deployment.',
    bullets: [
      'Shared docs across embedded and standalone experiences',
      'BYOK support across multiple model providers',
      'Deployment guidance for environments such as Railway',
    ],
    statLabel: 'Providers',
    statValue: `${PROVIDERS.length}+ ready`,
    icon: (className) => Icons.settings({ className }),
  },
]

const STORY_MODULES = [
  {
    id: 'vision',
    eyebrow: 'Why it works',
    title: 'A visual agent should understand the screen before it touches anything.',
    body:
      'Aegis treats screenshots as the operating surface. That lets the product move through complex layouts, popovers, and state changes without relying on brittle selectors.',
    bullets: [
      'Screenshot analysis on the live viewport',
      'Multimodal reasoning over layout and state',
      'Safer automation under UI drift',
    ],
    docsSlug: 'quickstart',
    docsLabel: 'Read quickstart',
  },
  {
    id: 'control',
    eyebrow: 'Operator control',
    title: 'The operator stays in charge the whole time.',
    body:
      'The signed-in shell is built around live control. Steering notes, interrupts, queue management, transcripts, and workflow capture all sit in the same operational surface.',
    bullets: [
      'Live sessions with frame, log, and workflow updates',
      'Steer, interrupt, and queue semantics built into the core loop',
      'Voice input and transcript-driven task starts',
    ],
    docsSlug: 'live-sessions',
    docsLabel: 'Read live session guide',
  },
  {
    id: 'integrations',
    eyebrow: 'Teams and outputs',
    title: 'Workflows and integrations turn successful runs into repeatable operations.',
    body:
      'Once the session finds a useful pattern, operators can save it, run it again, and connect outputs to integrations such as Telegram, Slack, and Discord.',
    bullets: [
      'Reusable workflow templates',
      'Operator-facing integration setup',
      'Docs and tutorials that explain the end-to-end path',
    ],
    docsSlug: 'integrations',
    docsLabel: 'Read integration docs',
  },
]

const DOCS_GATEWAY = [
  { slug: 'quickstart', title: 'Quickstart', description: 'Get from zero to a live session with the shortest possible setup path.' },
  { slug: 'api-auth-reference', title: 'API reference', description: 'HTTP routes, WebSocket contract, and auth endpoints in one place.' },
  { slug: 'first-live-run', title: 'Tutorials', description: 'Follow end-to-end operator examples without guessing the next step.' },
  { slug: 'faq', title: 'FAQ', description: 'Common auth, deployment, and operator questions answered directly.' },
  { slug: 'changelog', title: 'Changelog', description: 'Launch-facing updates and product changes as the surface evolves.' },
]

const TRUST_BANDS = [
  { label: 'Auth', value: 'Password, Google, GitHub, and OIDC SSO' },
  { label: 'Runtime', value: 'FastAPI, WebSockets, Playwright, and PostgreSQL' },
  { label: 'Models', value: 'Gemini, GPT, Claude, Mistral, and Groq' },
  { label: 'Deploy', value: 'Docker-first with Railway-ready backend support' },
]

export function LandingPage({ onGetStarted, onOpenDocsHome, onOpenDoc, docsPortalHref }: LandingPageProps) {
  const docsPortalBase = docsPortalHref.replace(/\/$/, '')

  return (
    <main className='min-h-screen bg-[#070b12] text-zinc-100'>
      <PublicHeader
        onGoHome={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
        onGoAuth={onGetStarted}
        onGoDocsHome={onOpenDocsHome}
        onGoDoc={onOpenDoc}
        docsPortalHref={docsPortalHref}
      />

      <section className='relative overflow-hidden'>
        <div className='absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(34,211,238,0.14),transparent_30%),radial-gradient(circle_at_bottom_right,rgba(56,189,248,0.12),transparent_35%)]' />
        <div className='relative mx-auto grid w-full max-w-7xl gap-14 px-6 py-20 lg:grid-cols-[1.02fr_0.98fr] lg:py-28'>
          <div className='flex flex-col justify-center'>
            <p className='text-[11px] uppercase tracking-[0.28em] text-cyan-200'>Story-led launch</p>
            <h1 className='mt-5 max-w-4xl text-5xl font-semibold leading-[1.02] text-white md:text-6xl'>
              Navigate any interface with a visual operator that can see, listen, and adapt.
            </h1>
            <p className='mt-6 max-w-2xl text-base leading-8 text-zinc-300 md:text-lg'>
              Aegis is an AI-powered universal UI navigator. It watches the screen, reasons over live state, and acts with the operator still in control from the first instruction to the last step.
            </p>
            <div className='mt-8 flex flex-wrap gap-3'>
              <button
                type='button'
                onClick={onGetStarted}
                className='rounded-full bg-cyan-500 px-6 py-3 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400'
              >
                Start from auth
              </button>
              <button
                type='button'
                onClick={() => onOpenDoc('quickstart')}
                className='rounded-full border border-white/10 px-6 py-3 text-sm text-zinc-100 transition hover:border-cyan-400/30 hover:bg-cyan-400/8'
              >
                Read quickstart
              </button>
              <a
                href={docsPortalHref}
                className='rounded-full border border-white/10 px-6 py-3 text-sm text-zinc-100 transition hover:border-cyan-400/30 hover:bg-cyan-400/8'
              >
                Open docs portal
              </a>
            </div>

            <div className='mt-10 flex flex-wrap items-center gap-4'>
              <p className='text-xs uppercase tracking-[0.22em] text-zinc-500'>Supported providers</p>
              <div className='flex flex-wrap gap-2'>
                {PROVIDERS.map((provider) => (
                  <span
                    key={provider.id}
                    title={provider.displayName}
                    className='inline-flex h-10 min-w-10 items-center justify-center rounded-2xl border border-white/8 bg-white/3 px-3 text-sm text-zinc-200'
                  >
                    {renderProviderIcon(provider, 'h-5 w-5')}
                  </span>
                ))}
              </div>
            </div>
          </div>

          <EntrySlider slides={LANDING_SLIDES} className='self-start lg:sticky lg:top-28' />
        </div>
      </section>

      <section className='mx-auto grid w-full max-w-7xl gap-10 px-6 py-8 md:grid-cols-4'>
        {TRUST_BANDS.map((band) => (
          <article key={band.label} className='rounded-3xl border border-white/8 bg-white/3 p-5'>
            <p className='text-[11px] uppercase tracking-[0.24em] text-zinc-500'>{band.label}</p>
            <p className='mt-3 text-sm leading-7 text-zinc-200'>{band.value}</p>
          </article>
        ))}
      </section>

      <section id='features' className='mx-auto w-full max-w-7xl px-6 py-18'>
        <div className='mb-10 max-w-2xl'>
          <p className='text-[11px] uppercase tracking-[0.24em] text-cyan-200'>Capability map</p>
          <h2 className='mt-4 text-4xl font-semibold text-white'>Everything needed to move from discovery to live execution.</h2>
          <p className='mt-4 text-sm leading-7 text-zinc-400'>
            This public surface has to do more than market the product. It needs to show operators, builders, and teammates how the system behaves before they ever sign in.
          </p>
        </div>
        <div className='grid gap-4 md:grid-cols-2 xl:grid-cols-3'>
          {FEATURES.map((feature) => (
            <article key={feature.title} className='rounded-[28px] border border-white/8 bg-[#0c1018] p-6'>
              <div className='inline-flex rounded-2xl border border-cyan-400/20 bg-cyan-400/8 p-3 text-cyan-200'>
                {feature.icon({ className: 'h-5 w-5' })}
              </div>
              <h3 className='mt-5 text-lg font-semibold text-white'>{feature.title}</h3>
              <p className='mt-3 text-sm leading-7 text-zinc-300'>{feature.description}</p>
            </article>
          ))}
        </div>
      </section>

      <section className='mx-auto flex w-full max-w-7xl flex-col gap-8 px-6 py-18'>
        <div className='max-w-2xl'>
          <p className='text-[11px] uppercase tracking-[0.24em] text-cyan-200'>Product story</p>
          <h2 className='mt-4 text-4xl font-semibold text-white'>An alternating story of control, vision, and operational readiness.</h2>
          <p className='mt-4 text-sm leading-7 text-zinc-400'>
            The public surface teaches the product by moving between narrative explanation, docs entry points, and proof of how the operator shell actually works.
          </p>
        </div>

        {STORY_MODULES.map((module, index) => (
          <article
            key={module.id}
            className={`grid gap-6 rounded-[32px] border border-white/8 bg-[#0c1018] p-8 lg:grid-cols-2 ${index % 2 === 1 ? 'lg:[&>*:first-child]:order-2' : ''}`}
          >
            <div className='flex flex-col justify-center'>
              <p className='text-[11px] uppercase tracking-[0.24em] text-cyan-200'>{module.eyebrow}</p>
              <h3 className='mt-4 text-3xl font-semibold text-white'>{module.title}</h3>
              <p className='mt-4 text-sm leading-8 text-zinc-300'>{module.body}</p>
              <div className='mt-6 flex flex-wrap gap-3'>
                <button
                  type='button'
                  onClick={() => onOpenDoc(module.docsSlug)}
                  className='rounded-full border border-white/10 px-4 py-2 text-sm text-zinc-100 transition hover:border-cyan-400/30 hover:bg-cyan-400/8'
                >
                  {module.docsLabel}
                </button>
                <a
                  href={`${docsPortalBase}/${module.docsSlug}`}
                  className='rounded-full border border-white/10 px-4 py-2 text-sm text-zinc-100 transition hover:border-cyan-400/30 hover:bg-cyan-400/8'
                >
                  Read in docs portal
                </a>
              </div>
            </div>

            <div className='grid gap-4'>
              {module.bullets.map((bullet) => (
                <div key={bullet} className='rounded-3xl border border-white/8 bg-white/4 p-5 text-sm leading-7 text-zinc-200'>
                  {bullet}
                </div>
              ))}
            </div>
          </article>
        ))}
      </section>

      <section id='how' className='mx-auto w-full max-w-7xl px-6 py-18'>
        <div className='rounded-[36px] border border-white/8 bg-[#0c1018] p-8 md:p-10'>
          <div className='max-w-3xl'>
            <p className='text-[11px] uppercase tracking-[0.24em] text-cyan-200'>How it works</p>
            <h2 className='mt-4 text-4xl font-semibold text-white'>A tight loop connects capture, reasoning, execution, and feedback.</h2>
            <p className='mt-4 text-sm leading-8 text-zinc-300'>
              The operator shell and docs should explain the same loop. The live product just makes that loop visible through frames, transcripts, logs, and workflow steps.
            </p>
          </div>
          <div className='mt-8 grid gap-4 md:grid-cols-4'>
            {STEPS.map((step, index) => (
              <article key={step.title} className='rounded-3xl border border-white/8 bg-white/4 p-5'>
                <div className='inline-flex h-9 w-9 items-center justify-center rounded-2xl bg-cyan-400/12 text-sm font-semibold text-cyan-200'>
                  {index + 1}
                </div>
                <h3 className='mt-4 text-lg font-semibold text-white'>{step.title}</h3>
                <p className='mt-3 text-sm leading-7 text-zinc-300'>{step.text}</p>
              </article>
            ))}
          </div>
          <div className='mt-8 flex flex-wrap gap-3'>
            <button
              type='button'
              onClick={() => onOpenDoc('api-auth-reference')}
              className='rounded-full border border-white/10 px-4 py-2 text-sm text-zinc-100 transition hover:border-cyan-400/30 hover:bg-cyan-400/8'
            >
              Read API reference
            </button>
            <button
              type='button'
              onClick={() => onOpenDoc('first-live-run')}
              className='rounded-full border border-white/10 px-4 py-2 text-sm text-zinc-100 transition hover:border-cyan-400/30 hover:bg-cyan-400/8'
            >
              Follow a tutorial
            </button>
          </div>
        </div>
      </section>

      <section className='mx-auto w-full max-w-7xl px-6 py-18'>
        <div className='rounded-[36px] border border-cyan-400/20 bg-[radial-gradient(circle_at_top_left,rgba(34,211,238,0.12),transparent_30%),#0c1018] p-8 md:p-10'>
          <div className='max-w-3xl'>
            <p className='text-[11px] uppercase tracking-[0.24em] text-cyan-200'>Docs gateway</p>
            <h2 className='mt-4 text-4xl font-semibold text-white'>Read docs where the story needs depth.</h2>
            <p className='mt-4 text-sm leading-8 text-zinc-300'>
              The landing page should not try to answer every technical question directly. It should route users into quickstart, API reference, tutorials, FAQ, and changelog at the exact points where confidence matters.
            </p>
          </div>
          <div className='mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-5'>
            {DOCS_GATEWAY.map((item) => (
              <button
                key={item.slug}
                type='button'
                onClick={() => onOpenDoc(item.slug)}
                className='rounded-3xl border border-white/8 bg-white/4 p-5 text-left transition hover:border-cyan-400/30 hover:bg-cyan-400/8'
              >
                <p className='text-sm font-semibold text-white'>{item.title}</p>
                <p className='mt-3 text-sm leading-7 text-zinc-300'>{item.description}</p>
              </button>
            ))}
          </div>
        </div>
      </section>

      <section className='mx-auto w-full max-w-7xl px-6 py-18'>
        <div className='grid gap-6 rounded-[36px] border border-white/8 bg-[#0c1018] p-8 lg:grid-cols-[1.1fr_0.9fr]'>
          <div>
            <p className='text-[11px] uppercase tracking-[0.24em] text-cyan-200'>Bring your own keys</p>
            <h2 className='mt-4 text-4xl font-semibold text-white'>Use the providers you already trust.</h2>
            <p className='mt-4 text-sm leading-8 text-zinc-300'>
              One branch added richer provider visuals and pricing. This merge keeps that work while preserving the docs-first public-site structure, so the landing page stays consistent with the current model catalog.
            </p>
            <ul className='mt-6 grid gap-3 text-sm text-zinc-200'>
              {[
                'Add keys for OpenAI, Anthropic, Google, Mistral, or Groq',
                'Use one settings surface for providers and model selection',
                'Pair BYOK setup with docs for auth, deployment, and workflows',
              ].map((item) => (
                <li key={item} className='flex items-start gap-2'>
                  {Icons.check({ className: 'mt-1 h-4 w-4 shrink-0 text-cyan-300' })}
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className='grid gap-3'>
            {PROVIDERS.slice(0, 4).map((provider) => (
              <div key={provider.id} className='flex items-center gap-3 rounded-3xl border border-white/8 bg-white/4 px-4 py-4'>
                <span className='inline-flex h-10 w-10 items-center justify-center rounded-2xl border border-white/10 bg-white/6 text-cyan-200'>
                  {renderProviderIcon(provider, 'h-5 w-5')}
                </span>
                <div>
                  <p className='text-sm font-medium text-white'>{provider.displayName}</p>
                  <p className='text-xs text-zinc-400'>{provider.models.length} models available</p>
                </div>
                <span className='ml-auto inline-flex items-center gap-2 rounded-full border border-emerald-400/20 bg-emerald-400/10 px-3 py-1 text-[11px] text-emerald-200'>
                  <span className='h-2 w-2 rounded-full bg-emerald-300' />
                  Ready
                </span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id='pricing' className='mx-auto w-full max-w-7xl px-6 py-18'>
        <div className='max-w-3xl'>
          <p className='text-[11px] uppercase tracking-[0.24em] text-cyan-200'>Pricing</p>
          <h2 className='mt-4 text-4xl font-semibold text-white'>Clear entry points for individual operators and teams.</h2>
          <p className='mt-4 text-sm leading-8 text-zinc-300'>
            This keeps the pricing work from the other branch while staying connected to docs and onboarding. Users can start with the public story, read the docs, and then pick the operating mode that fits.
          </p>
        </div>
        <div className='mt-8 grid gap-6 lg:grid-cols-3'>
          {PRICING.map((plan) => (
            <article
              key={plan.name}
              className={`rounded-[32px] border p-7 ${
                plan.highlight
                  ? 'border-cyan-400/35 bg-[linear-gradient(180deg,rgba(34,211,238,0.16),rgba(12,16,24,0.95))]'
                  : 'border-white/8 bg-[#0c1018]'
              }`}
            >
              {plan.highlight && (
                <p className='mb-4 text-[11px] uppercase tracking-[0.22em] text-cyan-200'>Most popular</p>
              )}
              <h3 className='text-2xl font-semibold text-white'>{plan.name}</h3>
              <div className='mt-3 flex items-end gap-1'>
                <span className='text-4xl font-semibold text-white'>{plan.price}</span>
                <span className='pb-1 text-sm text-zinc-400'>{plan.period}</span>
              </div>
              <p className='mt-4 text-sm leading-7 text-zinc-300'>{plan.description}</p>
              <button
                type='button'
                onClick={onGetStarted}
                className={`mt-6 w-full rounded-full px-4 py-3 text-sm font-medium transition ${
                  plan.highlight
                    ? 'bg-cyan-500 text-slate-950 hover:bg-cyan-400'
                    : 'border border-white/10 text-zinc-100 hover:border-cyan-400/30 hover:bg-cyan-400/8'
                }`}
              >
                {plan.cta}
              </button>
              <ul className='mt-6 grid gap-3 text-sm text-zinc-200'>
                {plan.features.map((feature) => (
                  <li key={feature} className='flex items-start gap-2'>
                    {Icons.check({ className: 'mt-1 h-4 w-4 shrink-0 text-cyan-300' })}
                    <span>{feature}</span>
                  </li>
                ))}
              </ul>
            </article>
          ))}
        </div>
      </section>

      <section className='mx-auto w-full max-w-7xl px-6 py-18'>
        <div className='grid gap-6 rounded-[36px] border border-white/8 bg-[#0c1018] p-8 lg:grid-cols-[1.2fr_0.8fr]'>
          <div>
            <p className='text-[11px] uppercase tracking-[0.24em] text-cyan-200'>Operator trust</p>
            <h2 className='mt-4 text-4xl font-semibold text-white'>Built to move from public discovery into a live operator shell.</h2>
            <p className='mt-4 text-sm leading-8 text-zinc-300'>
              The main product surface now carries users from a story-led launch page into authentication, embedded docs, the standalone docs portal, and finally the signed-in app without changing the core identity of the product.
            </p>
          </div>
          <div className='grid gap-4'>
            <div className='rounded-3xl border border-white/8 bg-white/4 p-5 text-sm leading-7 text-zinc-200'>
              Use embedded docs when users need context inside the main app, and the standalone docs portal when they need a deeper reference experience.
            </div>
            <div className='rounded-3xl border border-white/8 bg-white/4 p-5 text-sm leading-7 text-zinc-200'>
              Pricing, docs, auth, and the live operator shell now belong to the same public narrative instead of looking like separate products.
            </div>
            <div className='flex flex-wrap gap-3'>
              <button
                type='button'
                onClick={onGetStarted}
                className='rounded-full bg-cyan-500 px-4 py-2 text-sm font-medium text-slate-950 transition hover:bg-cyan-400'
              >
                Go to auth
              </button>
              <button
                type='button'
                onClick={onOpenDocsHome}
                className='rounded-full border border-white/10 px-4 py-2 text-sm text-zinc-100 transition hover:border-cyan-400/30 hover:bg-cyan-400/8'
              >
                Explore embedded docs
              </button>
            </div>
          </div>
        </div>
      </section>

      <PublicFooter
        onGoHome={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
        onGoAuth={onGetStarted}
        onGoDocsHome={onOpenDocsHome}
        onGoDoc={onOpenDoc}
        docsPortalHref={docsPortalHref}
      />
    </main>
  )
}
