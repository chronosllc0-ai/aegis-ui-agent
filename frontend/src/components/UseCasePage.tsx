import { useState } from 'react'
import { Icons } from './icons'
import { Reveal } from './Reveal'
import { PublicHeader } from '../public/PublicHeader'
import { getStandaloneDocUrl } from '../lib/site'

type UseCasePageProps = {
  useCaseId: string
  onBack: () => void
  onGetStarted: () => void
  onOpenDocsHome: () => void
  onOpenDoc: (slug: string) => void
}

type UseCase = {
  id: string
  category: string
  title: string
  longDescription: string
  prompts: { label: string; text: string }[]
  capabilities: string[]
}

const USE_CASES: UseCase[] = [
  {
    id: 'software-engineering',
    category: 'Engineering',
    title: 'Software Engineering',
    longDescription:
      'Aegis connects to your GitHub repository, understands the codebase structure, implements changes based on your instructions, and opens a properly described pull request. It handles the entire engineering loop — from reading issues to committing code — without you switching tabs.',
    prompts: [
      {
        label: 'PR from TODOs',
        text: 'Clone my acme/api repo, find every TODO comment in the codebase, implement the top 3, run the test suite, and open a PR targeting main with a clear description of what changed.',
      },
      {
        label: 'Bug fix PR',
        text: "Go through all open issues in acme/frontend labelled bug, pick the one with the most comments, read the relevant source file, write a fix, commit it, and open a draft PR.",
      },
    ],
    capabilities: [
      'GitHub repo cloning and editing',
      'Automated PR creation',
      'Test suite execution',
      'Issue triage and resolution',
    ],
  },
  {
    id: 'deep-research',
    category: 'Research',
    title: 'Deep Research & Competitive Intel',
    longDescription:
      'Aegis can spawn multiple focused sub-agents that research different sources simultaneously. Each sub-agent browses the web, extracts structured information, and reports back. Aegis then synthesizes everything into a coherent report and saves it as a file.',
    prompts: [
      {
        label: 'Database comparison',
        text: 'Research the top 5 open-source vector databases right now — compare them on license, performance benchmarks, and managed hosting options. Write a comparison table to a file.',
      },
      {
        label: 'Competitive landscape',
        text: 'Spawn three sub-agents in parallel: one to research Mistral AI, one to research Cohere, one to research Together AI. When all three are done, combine their findings into an investor-style competitive landscape summary.',
      },
    ],
    capabilities: [
      'Parallel sub-agent research',
      'Web search and extraction',
      'Structured report generation',
      'Multi-source synthesis',
    ],
  },
  {
    id: 'marketing-content',
    category: 'Marketing',
    title: 'Marketing & Content Ops',
    longDescription:
      'Aegis handles the full content production cycle. It researches competitor content, identifies gaps, writes to your tone of voice, and delivers finished assets. It can also scrape your existing content to learn your style before writing anything new.',
    prompts: [
      {
        label: 'SEO blog post',
        text: 'Research the SEO landscape for AI agent platforms — find the top 10 ranking articles, identify the content gaps none of them cover, and write a 1,500-word blog post targeting the gap with the highest search intent.',
      },
      {
        label: 'LinkedIn posts',
        text: 'Scrape our last 5 blog posts from mohex.org, identify the writing tone and structure, then write 3 LinkedIn posts promoting our new GitHub integration — match our voice exactly.',
      },
    ],
    capabilities: [
      'SEO research and gap analysis',
      'Content writing to brand voice',
      'Social copy generation',
      'Competitor content analysis',
    ],
  },
  {
    id: 'sales-research',
    category: 'Sales',
    title: 'Sales & Prospect Research',
    longDescription:
      "Before a sales call, Aegis researches the prospect end to end — funding history, tech stack from job listings, recent news, and executive activity on LinkedIn. It delivers a clean one-page brief you can read in 2 minutes.",
    prompts: [
      {
        label: 'Prospect brief',
        text: "Research Acme Corp — find their latest funding round, their tech stack from job listings, their CEO's recent LinkedIn activity, and any press mentions in the last 3 months. Write a one-page call brief.",
      },
      {
        label: 'Outreach drafts',
        text: "Go to LinkedIn, search for VP of Engineering roles at Series B fintech companies in London, extract the first 10 results, and write a personalised outreach draft for each one.",
      },
    ],
    capabilities: [
      'Company research via web',
      'LinkedIn profile extraction',
      'Tech stack identification',
      'Personalised outreach generation',
    ],
  },
  {
    id: 'legal-compliance',
    category: 'Legal',
    title: 'Legal & Compliance',
    longDescription:
      'Aegis monitors regulatory sources for changes relevant to your industry, extracts obligations from legal documents, and produces structured compliance checklists. It can read uploaded contract PDFs and flag non-standard clauses.',
    prompts: [
      {
        label: 'Compliance checklist',
        text: 'Find the latest EU AI Act compliance requirements for AI agents deployed in financial services. Summarise the 5 most critical obligations and write a compliance checklist to a markdown file.',
      },
      {
        label: 'Contract redline',
        text: "I've uploaded a vendor contract PDF. Read it, extract every clause that contains an indemnification or limitation of liability, flag any non-standard terms, and write a redline summary for our legal team.",
      },
    ],
    capabilities: [
      'Regulatory source monitoring',
      'PDF contract analysis',
      'Clause extraction and flagging',
      'Compliance documentation',
    ],
  },
  {
    id: 'data-analysis',
    category: 'Data',
    title: 'Data Analysis & Reporting',
    longDescription:
      'Aegis accepts uploaded CSV, JSON, or Excel files, writes and runs Python or Node.js scripts to analyse the data, and delivers clean output files. It iterates on errors automatically and explains what it found.',
    prompts: [
      {
        label: 'Customer deduplication',
        text: "I've uploaded a CSV with 10,000 customer records. Write and run a Python script to find duplicate emails, calculate the top 10 domains by customer count, and output a clean summary CSV.",
      },
      {
        label: 'Velocity chart',
        text: "Fetch our GitHub repo's commit history via the API, calculate commits per author per week for the last 3 months, and generate a bar chart showing team velocity trends.",
      },
    ],
    capabilities: [
      'CSV and JSON processing',
      'Python and Node.js execution',
      'Chart and visualisation generation',
      'Automated data cleaning',
    ],
  },
  {
    id: 'customer-success',
    category: 'Support',
    title: 'Customer Success & Support Ops',
    longDescription:
      'Aegis connects to your Slack or Telegram channels, reads incoming messages, identifies patterns and priorities, and either drafts responses for your review or replies automatically. It can search your docs to find accurate answers.',
    prompts: [
      {
        label: 'Feedback triage',
        text: 'Read the last 50 messages in my Slack #customer-feedback channel, identify the top 3 recurring complaints, categorise them by severity, and post a structured summary back in that channel.',
      },
      {
        label: 'Auto-reply bot',
        text: 'Monitor my Telegram bot for new support messages. For each one, search our docs site for the answer, draft a helpful reply, and send it back in the same chat automatically.',
      },
    ],
    capabilities: [
      'Slack and Telegram integration',
      'Message pattern analysis',
      'Automated reply drafting',
      'Docs-based answer retrieval',
    ],
  },
  {
    id: 'executive-ops',
    category: 'Operations',
    title: 'Executive Operations',
    longDescription:
      'Aegis runs scheduled automations on your behalf. Set up a cron once and it runs every day, week, or hour — scraping news, checking repos, posting digests, and keeping your team updated without you lifting a finger.',
    prompts: [
      {
        label: 'Daily news digest',
        text: 'Set up a daily 8am automation: search for the top 3 AI industry news stories, summarise each in 2 sentences, and post the digest to my Slack #exec-team channel.',
      },
      {
        label: 'PR reminder bot',
        text: 'Every Monday, check our GitHub repo for open PRs older than 7 days, list them with author and age, and post a reminder in #engineering with links to each one.',
      },
    ],
    capabilities: [
      'Cron-scheduled automations',
      'News aggregation and summarisation',
      'Slack and GitHub integration',
      'Recurring report generation',
    ],
  },
]

export function UseCasePage({
  useCaseId,
  onBack,
  onGetStarted,
  onOpenDocsHome,
  onOpenDoc,
}: UseCasePageProps) {
  const useCase = USE_CASES.find((uc) => uc.id === useCaseId) ?? USE_CASES[0]
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null)

  const copyPrompt = (text: string, index: number) => {
    void navigator.clipboard.writeText(text)
    setCopiedIndex(index)
    window.setTimeout(() => setCopiedIndex(null), 2000)
  }

  return (
    <main className='min-h-screen overflow-x-hidden bg-[#070b12] text-zinc-100'>
      <PublicHeader
        onGoHome={onBack}
        onGoAuth={onGetStarted}
        onGoDocsHome={onOpenDocsHome}
        onGoDoc={onOpenDoc}
        docsPortalHref={getStandaloneDocUrl()}
      />

      <div className='mx-auto w-full max-w-4xl px-4 py-10 sm:px-6 sm:py-16'>
        <Reveal mode='load' delayMs={40}>
          <button
            type='button'
            onClick={onBack}
            className='mb-8 flex items-center gap-2 text-sm text-zinc-400 transition hover:text-white'
          >
            {Icons.back({ className: 'h-4 w-4' })}
            Back to use cases
          </button>

          <p className='text-[11px] uppercase tracking-[0.28em] text-cyan-200'>{useCase.category}</p>
          <h1 className='mt-3 text-3xl font-semibold text-white sm:text-4xl md:text-5xl'>{useCase.title}</h1>
          <p className='mt-5 max-w-2xl text-base leading-8 text-zinc-300'>{useCase.longDescription}</p>
        </Reveal>

        {/* Video / image placeholder */}
        <Reveal mode='load' delayMs={120} className='mt-10'>
          <div className='overflow-hidden rounded-[24px] border border-white/8 bg-[#0c1018]'>
            <div className='relative w-full' style={{ paddingBottom: '56.25%' }}>
              <div className='absolute inset-0 flex flex-col items-center justify-center gap-4 bg-[#080b12]'>
                <div className='flex h-16 w-16 items-center justify-center rounded-full border border-cyan-400/30 bg-cyan-400/8'>
                  <svg viewBox='0 0 24 24' fill='none' className='h-7 w-7 text-cyan-300' aria-hidden='true'>
                    <path d='m9 7 9 5-9 5z' fill='currentColor' />
                  </svg>
                </div>
                <p className='text-sm text-zinc-400'>Demo video coming soon</p>
              </div>
            </div>
          </div>
        </Reveal>

        {/* Capabilities */}
        <Reveal mode='load' delayMs={160} className='mt-10'>
          <p className='text-[11px] uppercase tracking-[0.24em] text-cyan-200'>What Aegis uses</p>
          <div className='mt-4 flex flex-wrap gap-2'>
            {useCase.capabilities.map((cap) => (
              <span
                key={cap}
                className='rounded-full border border-white/8 bg-[#0c1018] px-4 py-1.5 text-sm text-zinc-300'
              >
                {cap}
              </span>
            ))}
          </div>
        </Reveal>

        {/* Prompts */}
        <Reveal mode='load' delayMs={200} className='mt-10'>
          <p className='text-[11px] uppercase tracking-[0.24em] text-cyan-200'>Try these prompts</p>
          <p className='mt-2 text-sm text-zinc-400'>Click any prompt to copy it, then paste it into Aegis.</p>
          <div className='mt-5 grid gap-4'>
            {useCase.prompts.map((prompt, index) => (
              <div
                key={prompt.label}
                role='button'
                tabIndex={0}
                className='group relative cursor-pointer rounded-[20px] border border-white/8 bg-[#0c1018] p-5 transition hover:border-cyan-400/30 hover:bg-cyan-400/4'
                onClick={() => copyPrompt(prompt.text, index)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') copyPrompt(prompt.text, index)
                }}
              >
                <div className='flex items-start justify-between gap-4'>
                  <div>
                    <p className='text-xs font-medium uppercase tracking-[0.18em] text-cyan-200'>{prompt.label}</p>
                    <p className='mt-3 text-sm leading-7 text-zinc-200'>{prompt.text}</p>
                  </div>
                  <span className='mt-0.5 shrink-0 text-zinc-500 transition group-hover:text-cyan-300'>
                    {copiedIndex === index
                      ? Icons.check({ className: 'h-4 w-4 text-emerald-400' })
                      : Icons.copy({ className: 'h-4 w-4' })}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </Reveal>

        {/* CTA */}
        <Reveal mode='load' delayMs={240} className='mt-12'>
          <div className='rounded-[24px] border border-cyan-400/20 bg-[radial-gradient(circle_at_top_left,rgba(34,211,238,0.10),transparent_50%),#0c1018] p-8 text-center'>
            <h2 className='text-xl font-semibold text-white'>Ready to try it?</h2>
            <p className='mx-auto mt-3 max-w-md text-sm leading-7 text-zinc-300'>
              Get started free. Connect your API keys and run this workflow in under a minute.
            </p>
            <button
              type='button'
              onClick={onGetStarted}
              className='mt-6 rounded-full bg-cyan-500 px-6 py-3 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400'
            >
              Get started free
            </button>
          </div>
        </Reveal>
      </div>
    </main>
  )
}
