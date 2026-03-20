import { EntrySlider, type EntrySlide } from './EntrySlider'
import { Icons } from './icons'
import { PROVIDERS, renderProviderIcon } from '../lib/models'
import { PublicFooter } from '../public/PublicFooter'
import { PublicHeader } from '../public/PublicHeader'
import { Reveal } from './Reveal'

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
    description: 'Get started with 1,000 credits and your own provider keys.',
    cta: 'Start free',
    ctaAction: 'auth' as const,
    features: [
      '1,000 credits included (1 credit = $0.001)',
      'BYOK sessions with all 5 providers',
      '32+ models across OpenAI, Anthropic, Google, Mistral, Groq',
      'Embedded docs access',
      'Real-time usage meter',
    ],
    highlight: false,
  },
  {
    name: 'Pro',
    price: '$29',
    period: '/month',
    description: 'For operators who need serious throughput and saved workflows.',
    cta: 'Start Pro trial',
    ctaAction: 'auth' as const,
    features: [
      '50,000 credits/month (~$50 of model usage)',
      'Everything in Free',
      'Workflow templates and session history',
      'Priority support',
      'Spending alerts and usage analytics',
    ],
    highlight: true,
  },
  {
    name: 'Team',
    price: '$79',
    period: '/seat/month',
    description: 'Shared operations, SSO, and team-level credit pools.',
    cta: 'Get started',
    ctaAction: 'auth' as const,
    features: [
      '200,000 credits/seat/month',
      'Everything in Pro',
      'Shared API key pools across the team',
      'Team workflow library',
      'SSO, admin dashboard, and audit logs',
    ],
    highlight: false,
  },
  {
    name: 'Enterprise',
    price: '$299',
    period: '/month',
    description: 'Dedicated support, custom limits, and advanced security for large teams.',
    cta: 'Talk to us',
    ctaAction: 'contact' as const,
    features: [
      '1,000,000+ credits/month (custom allocation)',
      'Everything in Team',
      'Dedicated account manager',
      'Custom model fine-tuning and hosting',
      'SAML SSO, SCIM provisioning, and audit exports',
      'SLA-backed uptime and priority engineering support',
    ],
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

// Provider highlight cards shown under the hero
const PROVIDER_HIGHLIGHTS = PROVIDERS.map((p) => ({
  id: p.id,
  name: p.displayName,
  count: p.models.length,
}))

const revealDelay = (index: number, base = 90) => index * base

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
            <Reveal mode='load' delayMs={40}>
              <p className='text-[11px] uppercase tracking-[0.28em] text-cyan-200'>A Chronos AI product</p>
              <h1 className='mt-5 max-w-4xl text-5xl font-semibold leading-[1.02] text-white md:text-6xl'>
                Navigate any interface with a visual operator that can see, listen, and adapt.
              </h1>
              <p className='mt-6 max-w-2xl text-base leading-8 text-zinc-300 md:text-lg'>
                Aegis is an AI-powered universal UI navigator. It watches the screen, reasons over live state, and acts with the operator still in control from the first instruction to the last step.
              </p>
            </Reveal>
            <Reveal mode='load' delayMs={180}>
              <div className='mt-8 flex flex-wrap gap-3'>
                <button
                  type='button'
                  onClick={onGetStarted}
                  className='rounded-full bg-cyan-500 px-6 py-3 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400'
                >
                  Get started free
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
            </Reveal>

            <Reveal mode='load' delayMs={280}>
              <div className='mt-10 flex flex-wrap items-center gap-4'>
                <p className='text-xs uppercase tracking-[0.22em] text-zinc-500'>Supported providers</p>
                <div className='flex flex-wrap gap-2'>
                  {PROVIDERS.map((provider) => (
                    <span
                      key={provider.id}
                      title={provider.displayName}
                      className='inline-flex h-9 w-9 items-center justify-center overflow-hidden rounded-full bg-[#111] ring-1 ring-white/[0.06]'
                    >
                      {renderProviderIcon(provider, 'h-7 w-7')}
                    </span>
                  ))}
                </div>
              </div>
            </Reveal>
          </div>

          <Reveal mode='load' delayMs={160} className='self-start lg:sticky lg:top-28'>
            <EntrySlider slides={LANDING_SLIDES} />
          </Reveal>
        </div>
      </section>

      <section className='mx-auto flex w-full max-w-7xl flex-wrap justify-center gap-4 px-6 py-8'>
        {PROVIDER_HIGHLIGHTS.map((ph) => {
          const provider = PROVIDERS.find((p) => p.id === ph.id)
          return (
            <Reveal key={ph.id} delayMs={revealDelay(PROVIDER_HIGHLIGHTS.indexOf(ph), 70)}>
              <article className='flex items-center gap-3 rounded-2xl border border-white/8 bg-[#0c1018] px-5 py-3'>
                {provider && <span className='inline-flex h-9 w-9 items-center justify-center overflow-hidden rounded-full bg-[#111] ring-1 ring-white/[0.06]'>{renderProviderIcon(provider, 'h-7 w-7')}</span>}
                <div>
                  <p className='text-sm font-medium text-white'>{ph.name}</p>
                  <p className='text-xs text-zinc-400'>{ph.count} models</p>
                </div>
              </article>
            </Reveal>
          )
        })}
      </section>

      <section id='features' className='mx-auto w-full max-w-7xl px-6 py-18'>
        <Reveal className='mb-10 max-w-2xl'>
          <p className='text-[11px] uppercase tracking-[0.24em] text-cyan-200'>Capability map</p>
          <h2 className='mt-4 text-4xl font-semibold text-white'>Everything needed to move from discovery to live execution.</h2>
          <p className='mt-4 text-sm leading-7 text-zinc-400'>
            This public surface has to do more than market the product. It needs to show operators, builders, and teammates how the system behaves before they ever sign in.
          </p>
        </Reveal>
        <div className='grid gap-4 md:grid-cols-2 xl:grid-cols-3'>
          {FEATURES.map((feature, index) => (
            <Reveal key={feature.title} delayMs={revealDelay(index)}>
              <article className='rounded-[28px] border border-white/8 bg-[#0c1018] p-6'>
                <div className='inline-flex rounded-2xl border border-cyan-400/20 bg-cyan-400/8 p-3 text-cyan-200'>
                  {feature.icon({ className: 'h-5 w-5' })}
                </div>
                <h3 className='mt-5 text-lg font-semibold text-white'>{feature.title}</h3>
                <p className='mt-3 text-sm leading-7 text-zinc-300'>{feature.description}</p>
              </article>
            </Reveal>
          ))}
        </div>
      </section>

      <section className='mx-auto flex w-full max-w-7xl flex-col gap-8 px-6 py-18'>
        <Reveal className='max-w-2xl'>
          <p className='text-[11px] uppercase tracking-[0.24em] text-cyan-200'>Product story</p>
          <h2 className='mt-4 text-4xl font-semibold text-white'>An alternating story of control, vision, and operational readiness.</h2>
          <p className='mt-4 text-sm leading-7 text-zinc-400'>
            The public surface teaches the product by moving between narrative explanation, docs entry points, and proof of how the operator shell actually works.
          </p>
        </Reveal>

        {STORY_MODULES.map((module, index) => (
          <Reveal key={module.id} delayMs={revealDelay(index, 110)}>
            <article
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
          </Reveal>
        ))}
      </section>

      <section id='how' className='mx-auto w-full max-w-7xl px-6 py-18'>
        <Reveal>
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
                <Reveal key={step.title} delayMs={revealDelay(index, 85)}>
                  <article className='rounded-3xl border border-white/8 bg-white/4 p-5'>
                    <div className='inline-flex h-9 w-9 items-center justify-center rounded-2xl bg-cyan-400/12 text-sm font-semibold text-cyan-200'>
                      {index + 1}
                    </div>
                    <h3 className='mt-4 text-lg font-semibold text-white'>{step.title}</h3>
                    <p className='mt-3 text-sm leading-7 text-zinc-300'>{step.text}</p>
                  </article>
                </Reveal>
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
        </Reveal>
      </section>

      <section className='mx-auto w-full max-w-7xl px-6 py-18'>
        <Reveal>
          <div className='rounded-[36px] border border-cyan-400/20 bg-[radial-gradient(circle_at_top_left,rgba(34,211,238,0.12),transparent_30%),#0c1018] p-8 md:p-10'>
            <div className='max-w-3xl'>
              <p className='text-[11px] uppercase tracking-[0.24em] text-cyan-200'>Docs gateway</p>
              <h2 className='mt-4 text-4xl font-semibold text-white'>Read docs where the story needs depth.</h2>
              <p className='mt-4 text-sm leading-8 text-zinc-300'>
                The landing page should not try to answer every technical question directly. It should route users into quickstart, API reference, tutorials, FAQ, and changelog at the exact points where confidence matters.
              </p>
            </div>
            <div className='mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-5'>
              {DOCS_GATEWAY.map((item, index) => (
                <Reveal key={item.slug} delayMs={revealDelay(index, 80)}>
                  <button
                    type='button'
                    onClick={() => onOpenDoc(item.slug)}
                    className='rounded-3xl border border-white/8 bg-white/4 p-5 text-left transition hover:border-cyan-400/30 hover:bg-cyan-400/8'
                  >
                    <p className='text-sm font-semibold text-white'>{item.title}</p>
                    <p className='mt-3 text-sm leading-7 text-zinc-300'>{item.description}</p>
                  </button>
                </Reveal>
              ))}
            </div>
          </div>
        </Reveal>
      </section>

      <section className='mx-auto w-full max-w-7xl px-6 py-18'>
        <Reveal>
          <div className='grid gap-6 rounded-[36px] border border-white/8 bg-[#0c1018] p-8 lg:grid-cols-[1.1fr_0.9fr]'>
            <div>
              <p className='text-[11px] uppercase tracking-[0.24em] text-cyan-200'>Bring your own keys</p>
              <h2 className='mt-4 text-4xl font-semibold text-white'>Use the providers you already trust.</h2>
              <p className='mt-4 text-sm leading-8 text-zinc-300'>
                Plug in your own API keys for any supported provider. Your keys are encrypted with AES-256, billed directly to your provider account, and never logged or shared.
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
              {PROVIDERS.slice(0, 4).map((provider, index) => (
                <Reveal key={provider.id} delayMs={revealDelay(index, 75)}>
                  <div className='flex items-center gap-3 rounded-3xl border border-white/8 bg-[#111] px-4 py-4'>
                    <span className='inline-flex h-10 w-10 items-center justify-center overflow-hidden rounded-full bg-[#111] ring-1 ring-white/[0.08]'>
                      {renderProviderIcon(provider, 'h-8 w-8')}
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
                </Reveal>
              ))}
            </div>
          </div>
        </Reveal>
      </section>

      <section id='pricing' className='mx-auto w-full max-w-7xl px-6 py-18'>
        <Reveal className='max-w-3xl'>
          <p className='text-[11px] uppercase tracking-[0.24em] text-cyan-200'>Pricing</p>
          <h2 className='mt-4 text-4xl font-semibold text-white'>Simple credit-based pricing. No hidden fees.</h2>
          <p className='mt-4 text-sm leading-8 text-zinc-300'>
            1 credit = $0.001. Every model call is metered transparently based on actual token usage with a simple 40% platform margin. Bring your own keys for zero-markup direct billing, or use platform credits for convenience.
          </p>
        </Reveal>
        <div className='mt-8 grid gap-6 lg:grid-cols-4'>
          {PRICING.map((plan, index) => (
            <Reveal key={plan.name} delayMs={revealDelay(index, 110)}>
              <article
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
                  onClick={() => {
                    if (plan.ctaAction === 'contact') {
                      onGetStarted()
                    } else {
                      onGetStarted()
                    }
                  }}
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
            </Reveal>
          ))}
        </div>
      </section>

      <section className='mx-auto w-full max-w-7xl px-6 py-18'>
        <Reveal>
          <div className='grid gap-6 rounded-[36px] border border-white/8 bg-[#0c1018] p-8 text-center'>
            <div>
              <h2 className='text-3xl font-semibold text-white'>Ready to automate with AI?</h2>
              <p className='mx-auto mt-4 max-w-xl text-sm leading-8 text-zinc-300'>
                Sign up, connect your API keys, and start running live sessions in under a minute. Read the docs when you need a deeper walkthrough.
              </p>
            </div>
            <div className='flex flex-wrap justify-center gap-3'>
              <button
                type='button'
                onClick={onGetStarted}
                className='rounded-full bg-cyan-500 px-5 py-2.5 text-sm font-medium text-slate-950 transition hover:bg-cyan-400'
              >
                Get started free
              </button>
              <button
                type='button'
                onClick={onOpenDocsHome}
                className='rounded-full border border-white/10 px-5 py-2.5 text-sm text-zinc-100 transition hover:border-cyan-400/30 hover:bg-cyan-400/8'
              >
                Read the docs
              </button>
            </div>
          </div>
        </Reveal>
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
