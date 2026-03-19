import { EntrySlider, type EntrySlide } from './EntrySlider'
import { Icons } from './icons'
import { PROVIDERS } from '../lib/models'

type LandingPageProps = {
  onGetStarted: () => void
  onOpenDocsHome: () => void
  onOpenDoc: (slug: string) => void
  docsPortalHref: string
}

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
  return (
    <main className='min-h-screen bg-[#0b0b0b] text-zinc-100'>
      {/* ── Nav ─────────────────────────────────────────────────────── */}
      <header className='mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-6'>
        <div className='flex items-center gap-2'>
          <img src='/shield.svg' alt='Aegis logo' className='h-7 w-7' />
          <span className='text-lg font-semibold'>Aegis</span>
          <span className='rounded-full border border-blue-500/40 px-2 py-0.5 text-[10px] text-blue-300'>by Chronos</span>
        </div>
        <nav className='flex items-center gap-4 text-sm text-zinc-300'>
          <a href='#features' className='hover:text-white'>Features</a>
          <a href='#how' className='hover:text-white'>How it works</a>
          <a href='#byok' className='hover:text-white'>BYOK</a>
          <a href='#pricing' className='hover:text-white'>Pricing</a>
          <button
            type='button'
            onClick={onGetStarted}
            className='rounded-md border border-blue-500/60 px-3 py-1.5 text-blue-200 hover:bg-blue-500/10'
          >
            Sign in
          </button>
        </nav>
      </header>

      {/* ── Hero ────────────────────────────────────────────────────── */}
      <section className='mx-auto grid w-full max-w-6xl grid-cols-1 items-center gap-10 px-6 py-20 lg:grid-cols-[1.2fr_1fr]'>
        <div>
          <p className='text-sm uppercase tracking-[0.2em] text-blue-300/80'>
            AI-powered universal UI agent
          </p>
          <h1 className='mt-4 text-4xl font-semibold leading-tight md:text-5xl'>
            Navigate any UI with
            <br />
            <span className='bg-gradient-to-r from-blue-400 to-cyan-300 bg-clip-text text-transparent'>
              vision, voice, and AI.
            </span>
          </h1>
          <p className='mt-5 max-w-lg text-base text-zinc-400'>
            Aegis sees your screen, reasons about intent, and acts with precision.
            Powered by your choice of model: Gemini, GPT-4.1, Claude, Mistral, or Groq,
            with full BYOK support.
          </p>
          <div className='mt-6 flex flex-wrap gap-3'>
            <button
              type='button'
              onClick={onGetStarted}
              className='rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-medium hover:bg-blue-500'
            >
              Get started free
            </button>
            <a
              href='#how'
              className='rounded-lg border border-[#2a2a2a] px-5 py-2.5 text-sm text-zinc-300 hover:border-blue-500/60'
            >
              See how it works
            </a>
          </div>
          <div className='mt-8 flex items-center gap-4'>
            <p className='text-xs text-zinc-500'>Supported providers</p>
            <div className='flex gap-2'>
              {PROVIDERS.map((p) => (
                <span
                  key={p.id}
                  title={p.displayName}
                  className='inline-flex h-7 w-7 items-center justify-center rounded-md border border-[#2a2a2a] bg-[#111] text-sm'
                >
                  {p.icon.startsWith('http') ? (
                    <img src={p.icon} alt={p.displayName} className='h-4 w-4' />
                  ) : (
                    p.icon
                  )}
                </span>
              ))}
            </div>
          </div>
        </div>
        <EntrySlider slides={LANDING_SLIDES} />
      </section>

      <section className='mx-auto grid w-full max-w-7xl gap-10 px-6 py-8 md:grid-cols-4'>
        {TRUST_BANDS.map((band) => (
          <article key={band.label} className='rounded-3xl border border-white/8 bg-white/3 p-5'>
            <p className='text-[11px] uppercase tracking-[0.24em] text-zinc-500'>{band.label}</p>
            <p className='mt-3 text-sm leading-7 text-zinc-200'>{band.value}</p>
          </article>
        ))}
      </section>

      <section className='mx-auto flex w-full max-w-7xl flex-col gap-8 px-6 py-18'>
        <div className='max-w-2xl'>
          <p className='text-[11px] uppercase tracking-[0.24em] text-cyan-200'>Product story</p>
          <h2 className='mt-4 text-4xl font-semibold text-white'>An alternating story of control, vision, and operational readiness.</h2>
          <p className='mt-4 text-sm leading-7 text-zinc-400'>
            The public surface should teach the product by moving between narrative explanation, docs entry points, and proof of how the operator shell actually works.
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
                  href={`${docsPortalHref.replace(/\/$/, '')}/${module.docsSlug}`}
                  className='rounded-full border border-white/10 px-4 py-2 text-sm text-zinc-100 transition hover:border-cyan-400/30 hover:bg-cyan-400/8'
                >
                  Read in docs portal
                </a>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── BYOK explainer ──────────────────────────────────────────── */}
      <section id='byok' className='mx-auto w-full max-w-6xl px-6 py-16'>
        <div className='rounded-2xl border border-[#1f1f1f] bg-[#111] p-8 md:p-10'>
          <div className='grid gap-8 md:grid-cols-2'>
            <div>
              <p className='text-sm uppercase tracking-[0.2em] text-blue-300/80'>Bring Your Own Key</p>
              <h2 className='mt-3 text-2xl font-semibold'>Your keys, your control</h2>
              <p className='mt-4 text-sm text-zinc-400'>
                Aegis encrypts your API keys with AES-256 before storing them.
                Each request is billed directly to your provider account.
                No middleman markup, no vendor lock-in.
              </p>
              <ul className='mt-5 space-y-2'>
                {[
                  'Add keys for OpenAI, Anthropic, Google, Mistral, or Groq',
                  'Keys encrypted at rest, never logged or shared',
                  'Remove or rotate keys anytime from Settings',
                  'Platform fallback when no user key is set',
                ].map((item) => (
                  <li key={item} className='flex items-start gap-2 text-sm text-zinc-300'>
                    {Icons.check({ className: 'mt-0.5 h-4 w-4 shrink-0 text-emerald-400' })}
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div className='flex items-center justify-center'>
              <div className='w-full max-w-xs space-y-3'>
                {PROVIDERS.slice(0, 4).map((p) => (
                  <div
                    key={p.id}
                    className='flex items-center gap-3 rounded-xl border border-[#1f1f1f] bg-[#0f0f0f] px-4 py-3'
                  >
                    <span className='text-lg'>
                      {p.icon.startsWith('http') ? (
                        <img src={p.icon} alt={p.displayName} className='h-5 w-5' />
                      ) : (
                        p.icon
                      )}
                    </span>
                    <span className='text-sm text-zinc-200'>{p.displayName}</span>
                    <span className='ml-auto inline-flex items-center gap-1 text-[11px] text-emerald-300'>
                      <span className='h-1.5 w-1.5 rounded-full bg-emerald-400' />
                      Connected
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </article>
        ))}
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
              Keep pricing for the next pass so this phase can focus on the product story, docs architecture, and onboarding flow.
            </div>
            <div className='rounded-3xl border border-white/8 bg-white/4 p-5 text-sm leading-7 text-zinc-200'>
              Use embedded docs when users need context inside the main app, and the standalone docs portal when they need a deeper reference experience.
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
