import { useState } from 'react'
import { Icons } from './icons'
import { PROVIDERS, renderProviderIcon } from '../lib/models'
import { PublicFooter } from '../public/PublicFooter'
import { PublicHeader } from '../public/PublicHeader'
import { Reveal } from './Reveal'
import { VideoPlaceholder } from './VideoPlaceholder'

export type PlanKey = 'pro' | 'team' | 'enterprise'

type LandingPageProps = {
  onGetStarted: () => void
  onOpenDocsHome: () => void
  onOpenDoc: (slug: string) => void
  docsPortalHref: string
  onBuyCredits?: (plan: PlanKey) => void
  onOpenUseCase?: (id: string) => void
}

// ─── Features / Capability Map ───────────────────────────────────────────────
const FEATURES = [
  {
    title: 'Vision first browser use',
    description:
      'Aegis reasons over the live screen state before every major action so the operator stays aligned with what is actually visible right now.',
    icon: Icons.globe,
  },
  {
    title: 'Real-time Agent Control',
    description:
      'Steer, interrupt, queue, and monitor transcripts without restarting the session or losing context.',
    icon: Icons.workflows,
  },
  {
    title: 'Persistent Memory',
    description:
      'Aegis stores facts, preferences, and decisions in semantic memory that persists across sessions - so it always knows your stack, your team, and how you like things done.',
    icon: Icons.star,
  },
  {
    title: 'Smart Automation',
    description:
      'Turn any task into a recurring cron job with a single prompt. Daily digests, weekly reports, PR reminders - scheduled and running without any code or settings UI.',
    icon: Icons.clock,
  },
  {
    title: 'Human in the loop approvals',
    description:
      'Aegis pauses at decision points, shows its plan, and waits for your go-ahead before touching anything sensitive. Confidence-based control you can adjust per tool.',
    icon: Icons.check,
  },
  {
    title: 'Sub agents Orchestration',
    description:
      'Spawn parallel agents that research, execute, and report simultaneously. Aegis coordinates their results into a single coherent output - faster than any single-thread tool.',
    icon: Icons.workflows,
  },
]

// ─── Competitor comparison ────────────────────────────────────────────────────
const COMPARISONS = [
  {
    task: 'Ad spend audit',
    competitor: 'ChatGPT',
    competitorAction: 'Tells you how to audit your ad spend.',
    aegisAction: 'Audits it. Hands you the PDF.',
  },
  {
    task: 'Meeting follow-ups',
    competitor: 'Copilot',
    competitorAction: 'Summarizes your meetings.',
    aegisAction: 'Creates the tasks, sends the follow-ups, updates the tracker.',
  },
  {
    task: 'Workflow automation',
    competitor: 'Zapier',
    competitorAction: 'Follows rules you write.',
    aegisAction: 'Figures out what needs automating and does it.',
  },
  {
    task: 'Building tools',
    competitor: 'Claude Code',
    competitorAction: 'Writes the code. You figure out the rest.',
    aegisAction: 'Builds it, ships it, sends you the link.',
  },
  {
    task: 'Research briefs',
    competitor: 'Perplexity',
    competitorAction: 'Searches and summarizes.',
    aegisAction: 'Researches, writes, formats, and delivers the file.',
  },
]

// ─── Use Cases ───────────────────────────────────────────────────────────────
const USE_CASE_ROWS = [
  {
    category: 'Founders & CEOs',
    cases: [
      { id: 'deep-research', label: 'Competitive intelligence reports' },
      { id: 'executive-ops', label: 'Daily briefing automations' },
      { id: 'data-analysis', label: 'KPI dashboards on demand' },
    ],
  },
  {
    category: 'Marketing & Growth',
    cases: [
      { id: 'marketing-content', label: 'SEO blog posts and content ops' },
      { id: 'sales-research', label: 'Prospect research and outreach' },
      { id: 'marketing-content', label: 'Social copy from existing content' },
    ],
  },
  {
    category: 'Engineering',
    cases: [
      { id: 'software-engineering', label: 'Clone repo → implement → open PR' },
      { id: 'software-engineering', label: 'Bug triage and fix automation' },
      { id: 'data-analysis', label: 'Codebase analytics and velocity charts' },
    ],
  },
  {
    category: 'Operations & Finance',
    cases: [
      { id: 'legal-compliance', label: 'Contract review and redline summaries' },
      { id: 'customer-success', label: 'Support triage and auto-reply' },
      { id: 'executive-ops', label: 'Recurring report and digest scheduling' },
    ],
  },
]

// ─── FAQ ─────────────────────────────────────────────────────────────────────
const FAQ_ITEMS = [
  {
    question: 'What is Aegis, exactly?',
    answer:
      'Aegis is an AI agent that can see your browser, write and run code, search the web, manage files, send messages, and work with your GitHub repositories - all from a single interface. It\'s not a chatbot. It completes tasks end to end.',
  },
  {
    question: 'How is Aegis different from ChatGPT or Claude?',
    answer:
      'ChatGPT and Claude give you text. Aegis gives you results. It can browse real websites, execute Python scripts, push commits to GitHub, post to Slack, and schedule recurring tasks - none of which those tools do natively.',
  },
  {
    question: 'What can Aegis actually do end to end?',
    answer:
      'It can: clone a GitHub repo → implement a feature → open a PR. Research 10 sources in parallel → write a report → save the file. Read your Slack channel → triage feedback → post a summary. Run a Python script on your uploaded data → output a CSV. The full capability list covers 53 tools across 10 clusters.',
  },
  {
    question: 'What integrations does Aegis support?',
    answer:
      'Built-in: Chromium browser, Python sandbox, Node.js sandbox, web search (DuckDuckGo), file system, memory, cron automations. With a key: GitHub (13 repo workflow tools), Slack, Telegram, Discord. Multi-LLM: Gemini, GPT-4o, Claude, Grok, OpenRouter (100+ models).',
  },
  {
    question: 'Do I need to provide my own API keys?',
    answer:
      'You can use platform credits without any keys. Or bring your own keys (BYOK) for zero-markup direct billing from your provider accounts. Keys are encrypted with AES-256 and never logged or shared.',
  },
  {
    question: 'Is there a free plan?',
    answer:
      'Yes. The free plan includes 1,000 credits (worth $1 of model usage) and full access to all features. No credit card required. When you need more, paid plans start at $29/month.',
  },
  {
    question: 'How does the credit system work?',
    answer:
      '1 credit = $0.001. Every model call is metered transparently based on actual token usage with a 40% platform margin. Use the real-time usage meter in your session to track spend as you go.',
  },
  {
    question: 'Can Aegis really push code to my GitHub?',
    answer:
      'Yes - with a Personal Access Token connected. Aegis clones your repo into an ephemeral session workspace, makes changes, commits them to a new branch, pushes, and opens a pull request via the GitHub CLI. The workspace is deleted when your session ends.',
  },
  {
    question: 'Is my data safe? What persists across sessions?',
    answer:
      'Session workspaces are ephemeral - files and cloned repos are wiped on disconnect. Memory is the only thing that persists: facts and preferences you explicitly tell Aegis to store. Nothing is shared between users.',
  },
  {
    question: 'What LLMs does Aegis support?',
    answer:
      'Google Gemini, OpenAI (GPT-5.2, GPT-5.1), Anthropic (Claude 4.6 Sonnet, Claude 4.5 Haiku), xAI (Grok), and any model available via OpenRouter - 40+ models and counting. You pick per session from the model selector.',
  },
]

// ─── Pricing ─────────────────────────────────────────────────────────────────
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
      '40+ models across OpenAI, Anthropic, Google, xAI, OpenRouter',
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

const CAPABILITY_CHECKS = [
  'Browser automation built-in',
  'Python and Node.js code execution',
  'GitHub repo engineering (13 tools)',
  'Slack, Telegram, and Discord integrations',
  'Persistent semantic memory',
  'Cron-scheduled automations',
  'Human-in-the-loop approval flows',
  'Parallel sub-agent orchestration',
  '6+ LLM providers, 40+ models',
  'BYOK - use your own API keys',
]

const PROVIDER_HIGHLIGHTS = PROVIDERS.map((p) => ({
  id: p.id,
  name: p.displayName,
  count: p.models.length,
}))

const revealDelay = (index: number, base = 90) => index * base

// ─── Sub-components ───────────────────────────────────────────────────────────

function FaqItem({ question, answer }: { question: string; answer: string }) {
  const [open, setOpen] = useState(false)
  return (
    <div className='border-b border-white/8'>
      <button
        type='button'
        onClick={() => setOpen((v) => !v)}
        className='flex w-full items-center justify-between gap-4 py-5 text-left text-sm font-medium text-white transition hover:text-cyan-200'
      >
        <span>{question}</span>
        <span className={`shrink-0 transition-transform ${open ? 'rotate-180' : ''}`}>
          {Icons.chevronDown({ className: 'h-4 w-4 text-zinc-400' })}
        </span>
      </button>
      {open && (
        <p className='pb-5 text-sm leading-7 text-zinc-300'>{answer}</p>
      )}
    </div>
  )
}

// ─── Main component ───────────────────────────────────────────────────────────

export function LandingPage({
  onGetStarted,
  onOpenDocsHome,
  onOpenDoc,
  docsPortalHref,
  onBuyCredits,
  onOpenUseCase,
}: LandingPageProps) {
  return (
    <main className='min-h-screen overflow-x-hidden bg-[#070b12] text-zinc-100'>
      <PublicHeader
        onGoHome={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
        onGoAuth={onGetStarted}
        onGoDocsHome={onOpenDocsHome}
        onGoDoc={onOpenDoc}
        docsPortalHref={docsPortalHref}
      />

      {/* ── HERO ─────────────────────────────────────────────────────────── */}
      <section className='relative overflow-hidden'>
        <div className='absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(34,211,238,0.14),transparent_30%),radial-gradient(circle_at_bottom_right,rgba(56,189,248,0.12),transparent_35%)]' />
        <div className='relative mx-auto grid w-full max-w-7xl gap-8 px-4 py-12 sm:gap-14 sm:px-6 sm:py-20 lg:grid-cols-[1.02fr_0.98fr] lg:py-28'>
          <div className='flex flex-col justify-center'>
            <Reveal mode='load' delayMs={40}>
              <p className='text-[11px] uppercase tracking-[0.28em] text-cyan-200'>A Chronos AI product</p>
              <h1 className='mt-4 max-w-4xl text-3xl font-semibold leading-[1.08] text-white sm:mt-5 sm:text-4xl md:text-5xl lg:text-6xl lg:leading-[1.02]'>
                Your AI coworker that actually ships.
              </h1>
              <p className='mt-4 max-w-2xl text-sm leading-7 text-zinc-300 sm:mt-6 sm:text-base sm:leading-8 md:text-lg'>
                Aegis is your AI coworker that actually browses, codes, researches, files PRs, sends messages, and schedules your recurring tasks end to end, without you switching tabs. Aegis combines the multimodal capabilities of frontier models like Gemini 3.1 pro and OpenAI GPT-5.4 to reason and use browser for research and software testing as it builds on the fly!
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
            <VideoPlaceholder />
          </Reveal>
        </div>
      </section>

      {/* ── PROVIDER CARDS ───────────────────────────────────────────────── */}
      <section className='mx-auto w-full max-w-7xl overflow-hidden px-4 py-6 sm:px-6 sm:py-8'>
        <div className='animate-marquee flex w-max gap-2 sm:gap-4'>
          {[...PROVIDER_HIGHLIGHTS, ...PROVIDER_HIGHLIGHTS].map((ph, i) => {
            const provider = PROVIDERS.find((p) => p.id === ph.id)
            return (
              <article key={`${ph.id}-${i}`} className='flex items-center gap-3 rounded-2xl border border-white/8 bg-[#0c1018] px-5 py-3'>
                {provider && (
                  <span className='inline-flex h-9 w-9 items-center justify-center overflow-hidden rounded-full bg-[#111] ring-1 ring-white/[0.06]'>
                    {renderProviderIcon(provider, 'h-7 w-7')}
                  </span>
                )}
                <div>
                  <p className='text-sm font-medium text-white'>{ph.name}</p>
                  <p className='text-xs text-zinc-400'>{ph.count} models</p>
                </div>
              </article>
            )
          })}
        </div>
      </section>

      {/* ── FEATURES / CAPABILITY MAP ────────────────────────────────────── */}
      <section id='features' className='mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 sm:py-18'>
        <Reveal className='mb-10 max-w-2xl'>
          <p className='text-[11px] uppercase tracking-[0.24em] text-cyan-200'>Aegis features and capabilities</p>
          <h2 className='mt-4 text-2xl font-semibold text-white sm:text-3xl md:text-4xl'>
            Everything you need to move from instruction to shipped output.
          </h2>
          <p className='mt-4 text-sm leading-7 text-zinc-400'>
            Aegis combines browser automation, code execution, persistent memory, scheduled automations, and multi-agent orchestration in a single operator surface - so nothing falls through the gap between tools.
          </p>
        </Reveal>
        <div className='grid gap-4 md:grid-cols-2 xl:grid-cols-3'>
          {FEATURES.map((feature, index) => (
            <Reveal key={feature.title} delayMs={revealDelay(index)}>
              <article className='flex flex-col rounded-[28px] border border-white/8 bg-[#0c1018] p-6'>
                {/* Image placeholder */}
                <div className='mb-5 flex h-32 w-full items-center justify-center overflow-hidden rounded-[16px] border border-white/6 bg-[#080b12]'>
                  <div className='flex flex-col items-center gap-2 text-zinc-600'>
                    <svg viewBox='0 0 24 24' fill='none' className='h-6 w-6' stroke='currentColor' strokeWidth='1.5' aria-hidden='true'>
                      <rect x='3' y='3' width='18' height='18' rx='3' />
                      <circle cx='8.5' cy='8.5' r='1.5' />
                      <path d='m21 15-5-5L5 21' />
                    </svg>
                    <span className='text-[10px] uppercase tracking-wider'>Image coming soon</span>
                  </div>
                </div>
                <div className='inline-flex items-center gap-2.5 text-cyan-200'>
                  <span className='inline-flex h-8 w-8 items-center justify-center rounded-full border border-cyan-400/30 bg-cyan-400/10'>
                    {feature.icon({ className: 'h-4.5 w-4.5' })}
                  </span>
                  <p className='text-sm font-semibold text-cyan-100'>{feature.title}</p>
                </div>
                <p className='mt-4 text-sm leading-7 text-zinc-300'>{feature.description}</p>
              </article>
            </Reveal>
          ))}
        </div>
      </section>

      {/* ── WHY YOU MUST SHIFT - COMPARISON ──────────────────────────────── */}
      <section className='mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 sm:py-18'>
        <Reveal className='max-w-2xl'>
          <p className='text-[11px] uppercase tracking-[0.24em] text-cyan-200'>The shift</p>
          <h2 className='mt-4 text-2xl font-semibold text-white sm:text-3xl md:text-4xl'>
            You've tried the AI tools. The work is still there.
          </h2>
          <p className='mt-4 text-sm leading-7 text-zinc-400'>
            ChatGPT. Claude. Zapier. Copilot. You're already using AI. You're also still doing the work.
          </p>
        </Reveal>

        <div className='mt-8 grid gap-4'>
          {COMPARISONS.map((c, index) => (
            <Reveal key={c.task} delayMs={revealDelay(index, 80)}>
              <div className='overflow-hidden rounded-[24px] border border-white/8 bg-[#0c1018]'>
                <p className='border-b border-white/6 px-6 py-3 text-[10px] uppercase tracking-[0.22em] text-zinc-500'>
                  {c.task}
                </p>
                <div className='grid gap-0 sm:grid-cols-2'>
                  <div className='flex items-center gap-3 border-b border-white/6 px-6 py-4 sm:border-b-0 sm:border-r'>
                    <span className='shrink-0 text-xs font-medium text-zinc-500'>{c.competitor}</span>
                    <p className='text-sm text-zinc-300'>{c.competitorAction}</p>
                  </div>
                  <div className='flex items-center gap-3 bg-cyan-400/4 px-6 py-4'>
                    <span className='shrink-0 rounded-full bg-cyan-500/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-cyan-300'>
                      Aegis
                    </span>
                    <p className='text-sm font-medium text-white'>{c.aegisAction}</p>
                  </div>
                </div>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* ── THE SOLUTION ─────────────────────────────────────────────────── */}
      <section className='mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 sm:py-18'>
        <Reveal>
          <div className='overflow-hidden rounded-[32px] border border-cyan-400/20 bg-[radial-gradient(circle_at_top_left,rgba(34,211,238,0.12),transparent_35%),#0c1018]'>
            <div className='grid gap-0 lg:grid-cols-2'>
              <div className='flex flex-col justify-center p-8 md:p-12'>
                <p className='text-[11px] uppercase tracking-[0.24em] text-cyan-200'>The solution</p>
                <h2 className='mt-4 text-2xl font-semibold text-white sm:text-3xl md:text-4xl'>
                  Just Aegis. Done.
                </h2>
                <p className='mt-5 text-sm leading-8 text-zinc-300'>
                  One instruction. Aegis browses, researches, codes, files the PR, and sends the Slack update. You review the result - you don't do the work.
                </p>
                <div className='mt-8 flex flex-wrap gap-3'>
                  <button
                    type='button'
                    onClick={onGetStarted}
                    className='rounded-full bg-cyan-500 px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400'
                  >
                    Get started free
                  </button>
                  <button
                    type='button'
                    onClick={() => onOpenDoc('quickstart')}
                    className='rounded-full border border-white/10 px-5 py-2.5 text-sm text-zinc-100 transition hover:border-cyan-400/30 hover:bg-cyan-400/8'
                  >
                    Read quickstart
                  </button>
                </div>
              </div>
              {/* Screenshot / image placeholder */}
              <div className='relative flex min-h-[260px] items-center justify-center border-l border-white/6 bg-[#080b12] lg:min-h-[380px]'>
                <div className='flex flex-col items-center gap-3 text-zinc-600'>
                  <svg viewBox='0 0 24 24' fill='none' className='h-8 w-8' stroke='currentColor' strokeWidth='1.5' aria-hidden='true'>
                    <rect x='3' y='3' width='18' height='18' rx='3' />
                    <circle cx='8.5' cy='8.5' r='1.5' />
                    <path d='m21 15-5-5L5 21' />
                  </svg>
                  <p className='text-sm'>Screenshot coming soon</p>
                </div>
              </div>
            </div>
          </div>
        </Reveal>
      </section>

      {/* ── USE CASES ────────────────────────────────────────────────────── */}
      <section id='use-cases' className='mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 sm:py-18'>
        <Reveal className='mb-8 max-w-2xl'>
          <p className='text-[11px] uppercase tracking-[0.24em] text-cyan-200'>Use cases</p>
          <h2 className='mt-4 text-2xl font-semibold text-white sm:text-3xl md:text-4xl'>
            What Aegis can own for your team.
          </h2>
          <p className='mt-4 text-sm leading-7 text-zinc-400'>
            Click any workflow to see exactly how Aegis handles it - with prompts you can run right now.
          </p>
        </Reveal>

        <div className='grid gap-4 lg:grid-cols-2'>
          {USE_CASE_ROWS.map((row, rIndex) => (
            <Reveal key={row.category} delayMs={revealDelay(rIndex, 80)}>
              <div className='rounded-[24px] border border-white/8 bg-[#0c1018] overflow-hidden'>
                <p className='border-b border-white/8 px-6 py-4 text-xs font-semibold uppercase tracking-[0.2em] text-zinc-400'>
                  {row.category}
                </p>
                <div className='divide-y divide-white/6'>
                  {row.cases.map((c) => (
                    <button
                      key={c.label}
                      type='button'
                      onClick={() => onOpenUseCase?.(c.id)}
                      className='flex w-full items-center justify-between gap-3 px-6 py-4 text-left text-sm text-zinc-200 transition hover:bg-white/4 hover:text-white'
                    >
                      <span>{c.label}</span>
                      {Icons.chevronRight({ className: 'h-4 w-4 shrink-0 text-zinc-600' })}
                    </button>
                  ))}
                </div>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* ── PROMPT GALLERY ───────────────────────────────────────────────── */}
      <section className='mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 sm:py-10'>
        <Reveal className='mb-8 max-w-2xl'>
          <p className='text-[11px] uppercase tracking-[0.24em] text-cyan-200'>Prompt gallery</p>
          <h2 className='mt-4 text-xl font-semibold text-white sm:text-2xl'>
            Ready-to-run workflows across every capability.
          </h2>
          <p className='mt-3 text-sm leading-7 text-zinc-400'>
            Sign in to browse 50+ curated templates and launch any workflow with one click.
          </p>
        </Reveal>
        <Reveal delayMs={80}>
          <button
            type='button'
            onClick={onGetStarted}
            className='rounded-full border border-white/10 px-5 py-2.5 text-sm text-zinc-100 transition hover:border-cyan-400/30 hover:bg-cyan-400/8'
          >
            Browse prompt gallery
          </button>
        </Reveal>
      </section>

      {/* ── FAQ ─────────────────────────────────────────────────────────── */}
      <section id='faq' className='mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 sm:py-18'>
        <Reveal className='mb-8 max-w-2xl'>
          <p className='text-[11px] uppercase tracking-[0.24em] text-cyan-200'>FAQ</p>
          <h2 className='mt-4 text-2xl font-semibold text-white sm:text-3xl md:text-4xl'>Common questions.</h2>
        </Reveal>
        <div className='max-w-3xl'>
          {FAQ_ITEMS.map((item, i) => (
            <Reveal key={item.question} delayMs={revealDelay(i, 40)}>
              <FaqItem question={item.question} answer={item.answer} />
            </Reveal>
          ))}
          <Reveal delayMs={revealDelay(FAQ_ITEMS.length, 40)} className='mt-6'>
            <button
              type='button'
              onClick={() => onOpenDoc('faq')}
              className='text-sm text-zinc-400 transition hover:text-cyan-300'
            >
              Show all questions in docs
            </button>
          </Reveal>
        </div>
      </section>

      {/* ── PRICING ──────────────────────────────────────────────────────── */}
      <section id='pricing' className='mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 sm:py-18'>
        <Reveal className='max-w-3xl'>
          <p className='text-[11px] uppercase tracking-[0.24em] text-cyan-200'>Pricing</p>
          <h2 className='mt-4 text-2xl font-semibold text-white sm:text-3xl md:text-4xl'>
            Start free. Pay only when you're ready.
          </h2>
          <p className='mt-4 text-sm leading-8 text-zinc-300'>
            Every feature. Every integration. Full access on the free plan. No credit card, no sales call, no catch. When you need more throughput, paid plans start at $29/month.
          </p>
        </Reveal>
        <div className='mt-6 grid gap-4 sm:mt-8 sm:gap-6 sm:grid-cols-2 lg:grid-cols-4'>
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
                    } else if (plan.name === 'Free') {
                      onGetStarted()
                    } else {
                      const planKey = plan.name.toLowerCase() as PlanKey
                      if (onBuyCredits) {
                        onBuyCredits(planKey)
                      } else {
                        onGetStarted()
                      }
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

        {/* Capability checklist under pricing */}
        <Reveal className='mt-10'>
          <div className='rounded-[24px] border border-white/8 bg-[#0c1018] p-6 md:p-8'>
            <p className='text-[11px] uppercase tracking-[0.22em] text-zinc-500'>Included on every plan</p>
            <div className='mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-3'>
              {CAPABILITY_CHECKS.map((cap) => (
                <div key={cap} className='flex items-center gap-2 text-sm text-zinc-200'>
                  {Icons.check({ className: 'h-4 w-4 shrink-0 text-cyan-300' })}
                  <span>{cap}</span>
                </div>
              ))}
            </div>
          </div>
        </Reveal>
      </section>

      {/* ── FINAL CTA ────────────────────────────────────────────────────── */}
      <section className='mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 sm:py-18'>
        <Reveal>
          <div className='grid gap-6 rounded-[36px] border border-white/8 bg-[#0c1018] p-8 text-center'>
            <div>
              <h2 className='text-2xl font-semibold text-white sm:text-3xl'>
                Ready to automate the work, not just the conversation?
              </h2>
              <p className='mx-auto mt-4 max-w-xl text-sm leading-8 text-zinc-300'>
                Sign up, connect your API keys, and start running live sessions in under a minute.
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
