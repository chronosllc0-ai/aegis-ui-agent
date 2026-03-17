import { Icons } from './icons'

type LandingPageProps = {
  onGetStarted: () => void
}

const FEATURES = [
  {
    title: 'Vision-first navigation',
    description: 'Aegis reads the screen directly and operates any UI without relying on DOM selectors.',
    icon: Icons.globe,
  },
  {
    title: 'Real-time steering',
    description: 'Steer, interrupt, or queue instructions while tasks run to keep the agent aligned.',
    icon: Icons.workflows,
  },
  {
    title: 'Live voice control',
    description: 'Stream voice input through the Live API and keep hands-free navigation fast.',
    icon: Icons.mic,
  },
  {
    title: 'Cloud-ready by design',
    description: 'Ship on Cloud Run with Firestore session state and Storage-backed screenshots.',
    icon: Icons.settings,
  },
]

const STEPS = [
  { title: 'Capture', text: 'Grab the current viewport as a screenshot to lock in the UI state.' },
  { title: 'Analyze', text: 'Gemini vision identifies interactive elements and page context.' },
  { title: 'Act', text: 'Playwright executes clicks, typing, scrolling, and navigation.' },
  { title: 'Report', text: 'Progress streams back through logs, frames, and voice.' },
]

export function LandingPage({ onGetStarted }: LandingPageProps) {
  return (
    <main className='min-h-screen bg-[#0b0b0b] text-zinc-100'>
      <header className='mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-6'>
        <div className='flex items-center gap-2'>
          <img src='/shield.svg' alt='Aegis logo' className='h-7 w-7' />
          <span className='text-lg font-semibold'>Aegis</span>
        </div>
        <div className='flex items-center gap-3 text-sm text-zinc-300'>
          <a href='#features' className='hover:text-white'>Features</a>
          <a href='#how' className='hover:text-white'>How it works</a>
          <a href='#architecture' className='hover:text-white'>Architecture</a>
          <button type='button' onClick={onGetStarted} className='rounded-md border border-blue-500/60 px-3 py-1.5 text-blue-200 hover:bg-blue-500/10'>
            Sign in
          </button>
        </div>
      </header>

      <section className='mx-auto grid w-full max-w-6xl grid-cols-1 items-center gap-10 px-6 py-16 lg:grid-cols-[1.2fr_1fr]'>
        <div>
          <p className='text-sm uppercase tracking-[0.2em] text-blue-300/80'>AI-powered universal UI navigator</p>
          <h1 className='mt-4 text-4xl font-semibold leading-tight md:text-5xl'>
            Operate any UI with vision, voice, and precise control.
          </h1>
          <p className='mt-5 text-base text-zinc-400'>
            Aegis understands screens visually, reasons about intent, and executes actions with Playwright.
            It is built for real-time steering and reliable task completion on modern web apps.
          </p>
          <div className='mt-6 flex flex-wrap gap-3'>
            <button type='button' onClick={onGetStarted} className='rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium hover:bg-blue-500'>
              Get started
            </button>
            <a href='#how' className='rounded-lg border border-[#2a2a2a] px-4 py-2 text-sm text-zinc-300 hover:border-blue-500/60'>
              See how it works
            </a>
          </div>
        </div>
        <div className='rounded-2xl border border-[#1f1f1f] bg-[#111] p-6'>
          <p className='text-xs uppercase tracking-[0.3em] text-zinc-500'>Session overview</p>
          <div className='mt-4 space-y-4'>
            {[
              'Live frames stream as the agent navigates.',
              'Action logs show reasoning and step progression.',
              'Voice transcripts appear alongside steering controls.',
            ].map((item) => (
              <div key={item} className='flex items-center gap-3 rounded-lg border border-[#1f1f1f] bg-[#0f0f0f] px-3 py-2 text-sm text-zinc-300'>
                {Icons.check({ className: 'h-4 w-4 text-blue-300' })}
                <span>{item}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id='features' className='mx-auto w-full max-w-6xl px-6 py-12'>
        <div className='mb-8'>
          <h2 className='text-2xl font-semibold'>Built for real operators</h2>
          <p className='mt-2 text-sm text-zinc-400'>Everything is wired for live APIs, low-latency control, and reliable UI automation.</p>
        </div>
        <div className='grid gap-4 md:grid-cols-2'>
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

      <section id='how' className='mx-auto w-full max-w-6xl px-6 py-12'>
        <div className='mb-8'>
          <h2 className='text-2xl font-semibold'>How it works</h2>
          <p className='mt-2 text-sm text-zinc-400'>A tight loop connects vision, reasoning, and action until the task is complete.</p>
        </div>
        <div className='grid gap-4 md:grid-cols-4'>
          {STEPS.map((step, index) => (
            <div key={step.title} className='rounded-2xl border border-[#1f1f1f] bg-[#111] p-4'>
              <p className='text-xs uppercase tracking-[0.2em] text-zinc-500'>Step {index + 1}</p>
              <h3 className='mt-2 text-lg font-semibold'>{step.title}</h3>
              <p className='mt-2 text-sm text-zinc-400'>{step.text}</p>
            </div>
          ))}
        </div>
      </section>

      <section id='architecture' className='mx-auto w-full max-w-6xl px-6 py-12'>
        <div className='rounded-2xl border border-[#1f1f1f] bg-[#111] p-6 md:p-8'>
          <div className='flex items-center gap-2 text-sm text-zinc-400'>
            {Icons.workflows({ className: 'h-4 w-4' })}
            <span>Architecture</span>
          </div>
          <h2 className='mt-3 text-2xl font-semibold'>Designed for production-ready deployments</h2>
          <p className='mt-3 text-sm text-zinc-400'>
            FastAPI manages websocket sessions, Gemini handles vision and voice, and Playwright executes
            UI interactions. Cloud Run, Firestore, and Cloud Storage keep the stack scalable.
          </p>
          <div className='mt-5 grid gap-3 md:grid-cols-3'>
            {[
              { label: 'Frontend', value: 'React + Vite + TypeScript' },
              { label: 'Backend', value: 'FastAPI + WebSockets + Playwright' },
              { label: 'AI', value: 'Gemini multimodal models + Live API' },
            ].map((item) => (
              <div key={item.label} className='rounded-xl border border-[#1f1f1f] bg-[#0f0f0f] p-4'>
                <p className='text-xs uppercase tracking-[0.2em] text-zinc-500'>{item.label}</p>
                <p className='mt-2 text-sm text-zinc-200'>{item.value}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className='mx-auto w-full max-w-6xl px-6 py-16'>
        <div className='rounded-2xl border border-blue-500/30 bg-gradient-to-br from-blue-600/20 via-[#111] to-[#111] p-8 text-center'>
          <h2 className='text-2xl font-semibold'>Ready to run a live session?</h2>
          <p className='mt-2 text-sm text-zinc-300'>Sign in to connect your APIs and start driving real tasks.</p>
          <button type='button' onClick={onGetStarted} className='mt-5 rounded-lg bg-blue-600 px-5 py-2 text-sm font-medium hover:bg-blue-500'>
            Sign in to Aegis
          </button>
        </div>
      </section>

      <footer className='border-t border-[#1f1f1f] py-6 text-center text-xs text-zinc-500'>
        Aegis UI Navigator · Gemini Live Agent Challenge 2026
      </footer>
    </main>
  )
}
