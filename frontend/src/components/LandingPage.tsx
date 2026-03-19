import { EntrySlider, type EntrySlide } from './EntrySlider'
import { Icons } from './icons'
import { PROVIDERS } from '../lib/models'
import { PublicFooter } from '../public/PublicFooter'
import { PublicHeader } from '../public/PublicHeader'

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
                    {provider.icon.startsWith('http') ? (
                      <img src={provider.icon} alt={provider.displayName} className='h-5 w-5 rounded-sm' />
                    ) : (
                      provider.icon
                    )}
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
