import { Icons } from './icons'
import { PROVIDERS } from '../lib/models'

type LandingPageProps = {
  onGetStarted: () => void
}

const FEATURES = [
  {
    title: 'Multi-model intelligence',
    description:
      'Switch between OpenAI, Anthropic, Google Gemini, Mistral, and Groq in one click. Pick the best model for every task.',
    icon: Icons.globe,
  },
  {
    title: 'Real-time steering',
    description:
      'Steer, interrupt, or queue instructions while tasks run. Keep the agent aligned without starting over.',
    icon: Icons.workflows,
  },
  {
    title: 'Live voice control',
    description:
      'Stream voice input through the Live API for hands-free navigation with sub-second transcription.',
    icon: Icons.mic,
  },
  {
    title: 'Bring Your Own Key',
    description:
      'Use your own API keys for any provider. Keys are encrypted at rest — you control your usage and billing.',
    icon: Icons.settings,
  },
  {
    title: 'Vision-first navigation',
    description:
      'Aegis reads the screen directly with multimodal vision. No DOM selectors, no brittle scripts.',
    icon: Icons.check,
  },
  {
    title: 'Deploy anywhere',
    description:
      'One-click Railway deploys, Docker support, and a PostgreSQL backend. Production-ready from day one.',
    icon: Icons.menu,
  },
]

const STEPS = [
  {
    title: 'Capture',
    text: 'Grab the current viewport as a screenshot to lock in the UI state.',
  },
  {
    title: 'Analyze',
    text: 'Multimodal vision identifies interactive elements and page context.',
  },
  {
    title: 'Act',
    text: 'Playwright executes clicks, typing, scrolling, and navigation.',
  },
  {
    title: 'Report',
    text: 'Progress streams back through logs, frames, and voice narration.',
  },
]

const PRICING = [
  {
    name: 'Free',
    price: '$0',
    period: '/month',
    description: 'Get started with your own API keys',
    cta: 'Start free',
    features: [
      'Unlimited sessions (BYOK)',
      'All providers supported',
      'Community support',
      'Self-hosted option',
    ],
    highlight: false,
  },
  {
    name: 'Pro',
    price: '$29',
    period: '/month',
    description: 'For power users and small teams',
    cta: 'Start Pro trial',
    features: [
      'Everything in Free',
      'Included API credits ($20/mo)',
      'Priority model access',
      'Workflow templates',
      'Email support',
    ],
    highlight: true,
  },
  {
    name: 'Team',
    price: '$79',
    period: '/seat/month',
    description: 'Collaboration and shared workflows',
    cta: 'Contact us',
    features: [
      'Everything in Pro',
      'Shared API key pools',
      'Team workflow library',
      'SSO / SAML',
      'Dedicated support',
      'Custom integrations',
    ],
    highlight: false,
  },
]

export function LandingPage({ onGetStarted }: LandingPageProps) {
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
            Powered by your choice of model — Gemini, GPT-4.1, Claude, Mistral, or Groq —
            with full BYOK support.
          </p>
          <div className='mt-6 flex flex-wrap gap-3'>
            <button
              type='button'
              onClick={onGetStarted}
              className='rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-medium hover:bg-blue-500'
            >
              Get started — it's free
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
        <div className='rounded-2xl border border-[#1f1f1f] bg-[#111] p-6'>
          <p className='text-xs uppercase tracking-[0.3em] text-zinc-500'>Live session preview</p>
          <div className='mt-4 space-y-4'>
            {[
              'Real-time frames stream as the agent navigates.',
              'Action logs show reasoning and step progression.',
              'Voice transcripts appear alongside steering controls.',
              'Switch models mid-session without losing context.',
            ].map((item) => (
              <div
                key={item}
                className='flex items-center gap-3 rounded-lg border border-[#1f1f1f] bg-[#0f0f0f] px-3 py-2 text-sm text-zinc-300'
              >
                {Icons.check({ className: 'h-4 w-4 shrink-0 text-blue-300' })}
                <span>{item}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Features ────────────────────────────────────────────────── */}
      <section id='features' className='mx-auto w-full max-w-6xl px-6 py-16'>
        <div className='mb-10 text-center'>
          <h2 className='text-3xl font-semibold'>Everything you need to automate the web</h2>
          <p className='mx-auto mt-3 max-w-xl text-sm text-zinc-400'>
            Multi-model support, real-time control, encrypted BYOK — designed for production use.
          </p>
        </div>
        <div className='grid gap-4 md:grid-cols-2 lg:grid-cols-3'>
          {FEATURES.map((feature) => (
            <div key={feature.title} className='rounded-2xl border border-[#1f1f1f] bg-[#111] p-5'>
              <div className='flex items-center gap-3'>
                <span className='rounded-md border border-blue-500/30 bg-blue-500/10 p-2 text-blue-200'>
                  {feature.icon({ className: 'h-5 w-5' })}
                </span>
                <h3 className='text-lg font-semibold'>{feature.title}</h3>
              </div>
              <p className='mt-3 text-sm text-zinc-400'>{feature.description}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── How it works ────────────────────────────────────────────── */}
      <section id='how' className='mx-auto w-full max-w-6xl px-6 py-16'>
        <div className='mb-10 text-center'>
          <h2 className='text-3xl font-semibold'>How it works</h2>
          <p className='mx-auto mt-3 max-w-xl text-sm text-zinc-400'>
            A tight loop connects vision, reasoning, and action until the task is done.
          </p>
        </div>
        <div className='grid gap-4 md:grid-cols-4'>
          {STEPS.map((step, index) => (
            <div key={step.title} className='rounded-2xl border border-[#1f1f1f] bg-[#111] p-4'>
              <div className='mb-2 inline-flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600/20 text-sm font-bold text-blue-300'>
                {index + 1}
              </div>
              <h3 className='text-lg font-semibold'>{step.title}</h3>
              <p className='mt-2 text-sm text-zinc-400'>{step.text}</p>
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
                  'Keys encrypted at rest — never logged or shared',
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
          </div>
        </div>
      </section>

      {/* ── Architecture ────────────────────────────────────────────── */}
      <section className='mx-auto w-full max-w-6xl px-6 py-16'>
        <div className='rounded-2xl border border-[#1f1f1f] bg-[#111] p-6 md:p-8'>
          <div className='flex items-center gap-2 text-sm text-zinc-400'>
            {Icons.workflows({ className: 'h-4 w-4' })}
            <span>Architecture</span>
          </div>
          <h2 className='mt-3 text-2xl font-semibold'>Built for production</h2>
          <p className='mt-3 text-sm text-zinc-400'>
            FastAPI manages websocket sessions, multi-provider LLM routing handles vision
            and reasoning, and Playwright executes UI interactions. PostgreSQL, Railway, and
            Docker keep the stack scalable and portable.
          </p>
          <div className='mt-5 grid gap-3 md:grid-cols-4'>
            {[
              { label: 'Frontend', value: 'React + Vite + Tailwind' },
              { label: 'Backend', value: 'FastAPI + WebSockets + Playwright' },
              { label: 'AI', value: '5 providers · 30+ models' },
              { label: 'Infra', value: 'Railway · PostgreSQL · Docker' },
            ].map((item) => (
              <div key={item.label} className='rounded-xl border border-[#1f1f1f] bg-[#0f0f0f] p-4'>
                <p className='text-xs uppercase tracking-[0.2em] text-zinc-500'>{item.label}</p>
                <p className='mt-2 text-sm text-zinc-200'>{item.value}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Pricing ─────────────────────────────────────────────────── */}
      <section id='pricing' className='mx-auto w-full max-w-6xl px-6 py-16'>
        <div className='mb-10 text-center'>
          <h2 className='text-3xl font-semibold'>Simple, transparent pricing</h2>
          <p className='mx-auto mt-3 max-w-xl text-sm text-zinc-400'>
            Start free with your own keys. Upgrade for included credits and team features.
          </p>
        </div>
        <div className='grid gap-6 md:grid-cols-3'>
          {PRICING.map((plan) => (
            <div
              key={plan.name}
              className={`rounded-2xl border p-6 ${
                plan.highlight
                  ? 'border-blue-500/60 bg-gradient-to-b from-blue-600/10 to-[#111]'
                  : 'border-[#1f1f1f] bg-[#111]'
              }`}
            >
              {plan.highlight && (
                <p className='mb-3 text-xs font-medium uppercase tracking-wider text-blue-300'>
                  Most popular
                </p>
              )}
              <h3 className='text-xl font-semibold'>{plan.name}</h3>
              <div className='mt-2 flex items-baseline gap-1'>
                <span className='text-3xl font-bold'>{plan.price}</span>
                <span className='text-sm text-zinc-400'>{plan.period}</span>
              </div>
              <p className='mt-2 text-sm text-zinc-400'>{plan.description}</p>
              <button
                type='button'
                onClick={onGetStarted}
                className={`mt-5 w-full rounded-lg px-4 py-2 text-sm font-medium ${
                  plan.highlight
                    ? 'bg-blue-600 hover:bg-blue-500'
                    : 'border border-[#2a2a2a] hover:border-blue-500/60'
                }`}
              >
                {plan.cta}
              </button>
              <ul className='mt-5 space-y-2'>
                {plan.features.map((feat) => (
                  <li key={feat} className='flex items-start gap-2 text-sm text-zinc-300'>
                    {Icons.check({ className: 'mt-0.5 h-4 w-4 shrink-0 text-blue-300' })}
                    <span>{feat}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>

      {/* ── CTA ─────────────────────────────────────────────────────── */}
      <section className='mx-auto w-full max-w-6xl px-6 py-16'>
        <div className='rounded-2xl border border-blue-500/30 bg-gradient-to-br from-blue-600/20 via-[#111] to-[#111] p-8 text-center'>
          <h2 className='text-2xl font-semibold'>Ready to automate with AI?</h2>
          <p className='mt-2 text-sm text-zinc-300'>
            Sign in, connect your API keys, and start running live sessions in under a minute.
          </p>
          <button
            type='button'
            onClick={onGetStarted}
            className='mt-5 rounded-lg bg-blue-600 px-6 py-2.5 text-sm font-medium hover:bg-blue-500'
          >
            Get started free
          </button>
        </div>
      </section>

      {/* ── Footer ──────────────────────────────────────────────────── */}
      <footer className='border-t border-[#1f1f1f] py-6 text-center text-xs text-zinc-500'>
        Aegis · A Chronos Intelligence Systems product · mohex.org
      </footer>
    </main>
  )
}
