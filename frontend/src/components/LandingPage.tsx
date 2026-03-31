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
    title: 'Vision-first navigation',
    description:
      'Aegis reasons over the live screen state before every major action so the operator stays aligned with what is actually visible right now.',
    icon: Icons.globe,
  },
  {
    title: 'Real-time control',
    description:
      'Steer, interrupt, queue, and monitor transcripts without restarting the session or losing context.',
    icon: Icons.workflows,
  },
  {
    title: 'Memory across sessions',
    description:
      'Aegis stores facts, preferences, and decisions in semantic memory that persists across sessions so it always knows your stack, your team, and how you like things done.',
    icon: Icons.star,
  },
  {
    title: 'Scheduled automations',
    description:
      'Turn any task into a recurring cron job with a single prompt. Daily digests, weekly reports, PR reminders, scheduled and running without any code or settings UI.',
    icon: Icons.clock,
  },
  {
    title: 'Human-in-the-loop approval',
    description:
      'Aegis pauses at decision points, shows its plan, and waits for your go-ahead before touching anything sensitive. Confidence-based control you can adjust per tool.',
    icon: Icons.check,
  },
  {
    title: 'Sub-agent orchestration',
    description:
      'Spawn parallel agents that research, execute, and report simultaneously. Aegis coordinates their results into a single coherent output, faster than any single-thread tool.',
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
    competitorLogo: <ChatGptLogo />,
  },
  {
    task: 'Meeting follow-ups',
    competitor: 'Copilot',
    competitorAction: 'Summarizes your meetings.',
    aegisAction: 'Creates the tasks, sends the follow-ups, updates the tracker.',
    competitorLogo: <CopilotLogo />,
  },
  {
    task: 'Workflow automation',
    competitor: 'Zapier',
    competitorAction: 'Follows rules you write.',
    aegisAction: 'Figures out what needs automating and does it.',
    competitorLogo: <ZapierLogo />,
  },
  {
    task: 'Building tools',
    competitor: 'Claude Code',
    competitorAction: 'Writes the code. You figure out the rest.',
    aegisAction: 'Builds it, ships it, sends you the link.',
    competitorLogo: <ClaudeCodeLogo />,
  },
  {
    task: 'Research briefs',
    competitor: 'Perplexity',
    competitorAction: 'Searches and summarizes.',
    aegisAction: 'Researches, writes, formats, and delivers the file.',
    competitorLogo: <PerplexityLogo />,
  },
]

// ─── Integrations ─────────────────────────────────────────────────────────────
const INTEGRATIONS = [
  { name: 'GitHub', color: '#f0f0f0', logo: <GithubIntLogo /> },
  { name: 'Slack', color: '#E01E5A', logo: <SlackIntLogo /> },
  { name: 'Telegram', color: '#24A1DE', logo: <TelegramIntLogo /> },
  { name: 'Discord', color: '#5865F2', logo: <DiscordIntLogo /> },
  { name: 'Google Drive', color: '#4285F4', logo: <GoogleDriveIntLogo /> },
  { name: 'Linear', color: '#5E6AD2', logo: <LinearIntLogo /> },
  { name: 'Notion', color: '#fff', logo: <NotionIntLogo /> },
  { name: 'Stripe', color: '#635BFF', logo: <StripeIntLogo /> },
  { name: 'Gmail', color: '#EA4335', logo: <GmailIntLogo /> },
  { name: 'Jira', color: '#0052CC', logo: <JiraIntLogo /> },
  { name: 'HubSpot', color: '#FF7A59', logo: <HubSpotIntLogo /> },
  { name: 'Figma', color: '#F24E1E', logo: <FigmaIntLogo /> },
]

// ─── Use Cases ───────────────────────────────────────────────────────────────
const USE_CASE_ROWS = [
  {
    category: 'Founders and CEOs',
    cases: [
      { id: 'deep-research', label: 'Competitive intelligence reports' },
      { id: 'executive-ops', label: 'Daily briefing automations' },
      { id: 'data-analysis', label: 'KPI dashboards on demand' },
    ],
  },
  {
    category: 'Marketing and Growth',
    cases: [
      { id: 'marketing-content', label: 'SEO blog posts and content ops' },
      { id: 'sales-research', label: 'Prospect research and outreach' },
      { id: 'marketing-content', label: 'Social copy from existing content' },
    ],
  },
  {
    category: 'Engineering',
    cases: [
      { id: 'software-engineering', label: 'Clone repo, implement, open PR' },
      { id: 'software-engineering', label: 'Bug triage and fix automation' },
      { id: 'data-analysis', label: 'Codebase analytics and velocity charts' },
    ],
  },
  {
    category: 'Operations and Finance',
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
      "Aegis is an AI agent that can see your browser, write and run code, search the web, manage files, send messages, and work with your GitHub repositories from a single interface. It's not a chatbot. It completes tasks end to end.",
  },
  {
    question: 'How is Aegis different from ChatGPT or Claude?',
    answer:
      'ChatGPT and Claude give you text. Aegis gives you results. It can browse real websites, execute Python scripts, push commits to GitHub, post to Slack, and schedule recurring tasks, none of which those tools do natively.',
  },
  {
    question: 'What can Aegis actually do end to end?',
    answer:
      'It can: clone a GitHub repo, implement a feature, open a PR. Research 10 sources in parallel, write a report, save the file. Read your Slack channel, triage feedback, post a summary. Run a Python script on your uploaded data, output a CSV. The full capability list covers 53 tools across 10 clusters.',
  },
  {
    question: 'What integrations does Aegis support?',
    answer:
      'Built-in: Chromium browser, Python sandbox, Node.js sandbox, web search, file system, memory, cron automations. With a key: GitHub (13 repo workflow tools), Slack, Telegram, Discord. Multi-LLM: Gemini, GPT-4o, Claude, Grok, OpenRouter (100+ models).',
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
      'Yes, with a Personal Access Token connected. Aegis clones your repo into an ephemeral session workspace, makes changes, commits them to a new branch, pushes, and opens a pull request via the GitHub CLI. The workspace is deleted when your session ends.',
  },
  {
    question: 'Is my data safe? What persists across sessions?',
    answer:
      'Session workspaces are ephemeral. Files and cloned repos are wiped on disconnect. Memory is the only thing that persists: facts and preferences you explicitly tell Aegis to store. Nothing is shared between users.',
  },
  {
    question: 'What LLMs does Aegis support?',
    answer:
      'Google Gemini, OpenAI (GPT-4o, o3-mini), Anthropic (Claude 3.5 Sonnet, Claude 3 Haiku), xAI (Grok), and any model available via OpenRouter. 40+ models and counting. You pick per session from the model selector.',
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
  'BYOK, use your own API keys',
]

const PROVIDER_HIGHLIGHTS = PROVIDERS.map((p) => ({
  id: p.id,
  name: p.displayName,
  count: p.models.length,
}))

const revealDelay = (index: number, base = 90) => index * base

// ─── Brand logo sub-components (inline SVG, no external deps) ────────────────

function AegisShieldLogo({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox='0 0 64 64' fill='none' aria-hidden='true'>
      <path d='M32 6L54 14V30C54 44 44.5 54.5 32 58C19.5 54.5 10 44 10 30V14L32 6Z' fill='#1a1a1a' stroke='#22d3ee' strokeWidth='4' />
      <path d='M22 31L29 38L42 24' stroke='#22d3ee' strokeWidth='4' strokeLinecap='round' strokeLinejoin='round' />
    </svg>
  )
}

function ChatGptLogo() {
  return (
    <svg width='18' height='18' viewBox='0 0 41 41' fill='none' aria-hidden='true'>
      <path d='M37.5 20.5C37.5 21.9 37.3 23.3 36.9 24.6C35.7 29.1 32.4 32.8 28 34.6C26.1 35.4 24 35.8 21.8 35.8C15.3 35.8 9.7 31.9 7.3 26.3H7.2C7.2 26.3 7.2 26.2 7.2 26.2C6.3 24.1 5.8 21.8 5.8 19.4C5.8 19.1 5.8 18.8 5.8 18.5C6 12.1 9.7 6.6 15.1 4C16.9 3.1 19 2.5 21.2 2.5C22.7 2.5 24.1 2.7 25.5 3.2C30.6 4.8 34.6 8.9 36.2 14.1C37 16 37.5 18.2 37.5 20.5Z' fill='white' />
      <path d='M37.5 20.5C37.5 21.9 37.3 23.3 36.9 24.6L28.7 20.7L37.4 14.1C37.4 16 37.5 18.2 37.5 20.5Z' fill='#10a37f' />
      <path d='M36.2 14.1L28.7 20.7L25.5 3.2C30.6 4.8 34.6 8.9 36.2 14.1Z' fill='#10a37f' />
      <path d='M21.2 2.5C22.7 2.5 24.1 2.7 25.5 3.2L22.3 20.3L15.1 4C16.9 3.1 19 2.5 21.2 2.5Z' fill='#10a37f' />
      <path d='M7.3 26.3L15.1 4L22.3 20.3L7.3 26.3Z' fill='#10a37f' />
      <path d='M5.8 18.5C6 12.1 9.7 6.6 15.1 4L22.3 20.3L7.2 26.2L5.8 18.5Z' fill='#10a37f' />
    </svg>
  )
}

function CopilotLogo() {
  return (
    <svg width='18' height='18' viewBox='0 0 24 24' fill='none' aria-hidden='true'>
      <path d='M12 2C9 2 6.5 4 6.5 6.5C6.5 8.3 7.6 9.8 9.2 10.5C8.5 11.2 8 12.2 8 13.3V20C8 21.1 8.9 22 10 22H14C15.1 22 16 21.1 16 20V13.3C16 12.2 15.5 11.2 14.8 10.5C16.4 9.8 17.5 8.3 17.5 6.5C17.5 4 15 2 12 2Z' fill='#0078D4' />
      <circle cx='10' cy='13.5' r='1' fill='white' />
      <circle cx='14' cy='13.5' r='1' fill='white' />
    </svg>
  )
}

function ZapierLogo() {
  return (
    <svg width='18' height='18' viewBox='0 0 28 28' fill='none' aria-hidden='true'>
      <circle cx='14' cy='14' r='14' fill='#FF4A00' />
      <path d='M14 5L16.5 12H22L17.5 16L19.5 23L14 19L8.5 23L10.5 16L6 12H11.5L14 5Z' fill='white' />
    </svg>
  )
}

function ClaudeCodeLogo() {
  return (
    <svg width='18' height='18' viewBox='0 0 32 32' fill='none' aria-hidden='true'>
      <circle cx='16' cy='16' r='16' fill='#CC785C' />
      <path d='M9 21L13 11L16 18L19 13L23 21' stroke='white' strokeWidth='2' strokeLinecap='round' strokeLinejoin='round' />
    </svg>
  )
}

function PerplexityLogo() {
  return (
    <svg width='18' height='18' viewBox='0 0 32 32' fill='none' aria-hidden='true'>
      <circle cx='16' cy='16' r='16' fill='#20B2AA' />
      <path d='M10 22L16 10L22 22M13 18H19' stroke='white' strokeWidth='2' strokeLinecap='round' strokeLinejoin='round' />
    </svg>
  )
}

// ─── Integration logos ────────────────────────────────────────────────────────

function GithubIntLogo() {
  return (
    <svg width='22' height='22' viewBox='0 0 24 24' fill='currentColor' aria-hidden='true' className='text-zinc-200'>
      <path d='M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0 1 12 6.844a9.59 9.59 0 0 1 2.504.337c1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.02 10.02 0 0 0 22 12.017C22 6.484 17.522 2 12 2Z' />
    </svg>
  )
}

function SlackIntLogo() {
  return (
    <svg width='22' height='22' viewBox='0 0 24 24' fill='none' aria-hidden='true'>
      <path d='M5.042 15.165a2.528 2.528 0 0 1-2.52 2.523A2.528 2.528 0 0 1 0 15.165a2.527 2.527 0 0 1 2.522-2.52h2.52v2.52zM6.313 15.165a2.527 2.527 0 0 1 2.521-2.52 2.527 2.527 0 0 1 2.521 2.52v6.313A2.528 2.528 0 0 1 8.834 24a2.528 2.528 0 0 1-2.521-2.522v-6.313zM8.834 5.042a2.528 2.528 0 0 1-2.521-2.52A2.528 2.528 0 0 1 8.834 0a2.528 2.528 0 0 1 2.521 2.522v2.52H8.834zM8.834 6.313a2.528 2.528 0 0 1 2.521 2.521 2.528 2.528 0 0 1-2.521 2.521H2.522A2.528 2.528 0 0 1 0 8.834a2.528 2.528 0 0 1 2.522-2.521h6.312zM18.956 8.834a2.528 2.528 0 0 1 2.522-2.521A2.528 2.528 0 0 1 24 8.834a2.528 2.528 0 0 1-2.522 2.521h-2.522V8.834zM17.688 8.834a2.528 2.528 0 0 1-2.523 2.521 2.527 2.527 0 0 1-2.52-2.521V2.522A2.527 2.527 0 0 1 15.165 0a2.528 2.528 0 0 1 2.523 2.522v6.312zM15.165 18.956a2.528 2.528 0 0 1 2.523 2.522A2.528 2.528 0 0 1 15.165 24a2.527 2.527 0 0 1-2.52-2.522v-2.522h2.52zM15.165 17.688a2.527 2.527 0 0 1-2.52-2.523 2.526 2.526 0 0 1 2.52-2.52h6.313A2.527 2.527 0 0 1 24 15.165a2.528 2.528 0 0 1-2.522 2.523h-6.313z' fill='#E01E5A' />
    </svg>
  )
}

function TelegramIntLogo() {
  return (
    <svg width='22' height='22' viewBox='0 0 24 24' fill='none' aria-hidden='true'>
      <circle cx='12' cy='12' r='12' fill='#24A1DE' />
      <path d='M5.5 11.5l10-4-4 10-2-3.5L5.5 11.5z' fill='white' />
      <path d='M9.5 14l6.5-6.5' stroke='#24A1DE' strokeWidth='1' />
    </svg>
  )
}

function DiscordIntLogo() {
  return (
    <svg width='22' height='22' viewBox='0 0 24 24' fill='none' aria-hidden='true'>
      <circle cx='12' cy='12' r='12' fill='#5865F2' />
      <path d='M16.5 7.5C15.5 7 14.3 6.8 13 6.7L12.7 7.3C14 7.5 15.1 7.9 16 8.5C14.7 7.8 13.4 7.5 12 7.5C10.6 7.5 9.3 7.8 8 8.5C8.9 7.9 10.1 7.5 11.3 7.3L11 6.7C9.7 6.8 8.5 7 7.5 7.5C6.3 9.6 5.7 12 5.8 14.3C6.7 15.4 8 16.1 9.3 16.1L9.8 15.4C9 15.1 8.3 14.6 7.8 14C8.8 14.6 10.3 15 12 15C13.7 15 15.2 14.6 16.2 14C15.7 14.6 15 15.1 14.2 15.4L14.7 16.1C16 16.1 17.3 15.4 18.2 14.3C18.3 12 17.7 9.6 16.5 7.5ZM10 13C9.4 13 9 12.6 9 12C9 11.4 9.4 11 10 11C10.6 11 11 11.4 11 12C11 12.6 10.6 13 10 13ZM14 13C13.4 13 13 12.6 13 12C13 11.4 13.4 11 14 11C14.6 11 15 11.4 15 12C15 12.6 14.6 13 14 13Z' fill='white' />
    </svg>
  )
}

function GoogleDriveIntLogo() {
  return (
    <svg width='22' height='22' viewBox='0 0 87.3 78' fill='none' aria-hidden='true'>
      <path d='M6.6 66.85l3.85 6.65c.8 1.4 1.95 2.5 3.3 3.3l13.75-23.8H0c0 1.55.4 3.1 1.2 4.5l5.4 9.35z' fill='#0066DA' />
      <path d='M43.65 25L29.9 1.2C28.55 2 27.4 3.1 26.6 4.5L1.2 48.5C.4 49.9 0 51.45 0 53h27.5L43.65 25z' fill='#00AC47' />
      <path d='M73.55 76.8c1.35-.8 2.5-1.9 3.3-3.3l1.6-2.75 7.65-13.25c.8-1.4 1.2-2.95 1.2-4.5H60l5.85 12.05 7.7 11.75z' fill='#EA4335' />
      <path d='M43.65 25L57.4 1.2C56.05.4 54.5 0 52.95 0H34.35c-1.55 0-3.1.45-4.45 1.2L43.65 25z' fill='#00832D' />
      <path d='M60.1 53H27.5L13.75 76.8c1.35.8 2.9 1.2 4.45 1.2H69.1c1.55 0 3.1-.4 4.45-1.2L60.1 53z' fill='#2684FC' />
      <path d='M73.4 26.5L60.7 4.5C59.9 3.1 58.75 2 57.4 1.2L43.65 25l16.45 28H87.3c0-1.55-.4-3.1-1.2-4.5l-12.7-22z' fill='#FFBA00' />
    </svg>
  )
}

function LinearIntLogo() {
  return (
    <svg width='22' height='22' viewBox='0 0 100 100' fill='none' aria-hidden='true'>
      <circle cx='50' cy='50' r='50' fill='#5E6AD2' />
      <path d='M20 66L50 20L80 66H20Z' fill='white' fillOpacity='0.9' />
      <path d='M30 70H70' stroke='white' strokeWidth='6' strokeLinecap='round' />
    </svg>
  )
}

function NotionIntLogo() {
  return (
    <svg width='22' height='22' viewBox='0 0 24 24' fill='none' aria-hidden='true'>
      <rect width='24' height='24' rx='4' fill='#fff' />
      <path d='M6.5 5h8l3 3v11h-11V5z' fill='#1a1a1a' />
      <path d='M14.5 5v3h3' stroke='white' strokeWidth='0.5' />
      <rect x='8' y='10' width='7' height='1' rx='0.5' fill='white' fillOpacity='0.7' />
      <rect x='8' y='12.5' width='5' height='1' rx='0.5' fill='white' fillOpacity='0.7' />
      <rect x='8' y='15' width='6' height='1' rx='0.5' fill='white' fillOpacity='0.7' />
    </svg>
  )
}

function StripeIntLogo() {
  return (
    <svg width='22' height='22' viewBox='0 0 24 24' fill='none' aria-hidden='true'>
      <rect width='24' height='24' rx='4' fill='#635BFF' />
      <path d='M11.5 9.5c0-.8.7-1.1 1.8-1.1 1.6 0 3.6.5 5 1.2V5.3A13.3 13.3 0 0 0 13.2 4C9.8 4 7.5 5.7 7.5 8.7c0 4.6 6.3 3.9 6.3 5.9 0 .9-.8 1.2-2 1.2-1.7 0-3.9-.7-5.6-1.7V18a13.4 13.4 0 0 0 5.6 1.2c3.5 0 5.9-1.7 5.9-4.8C17.7 9.8 11.5 10.6 11.5 9.5Z' fill='white' />
    </svg>
  )
}

function GmailIntLogo() {
  return (
    <svg width='22' height='22' viewBox='0 0 24 24' fill='none' aria-hidden='true'>
      <path d='M24 5.457v13.909c0 .904-.732 1.636-1.636 1.636h-3.819V11.73L12 16.64l-6.545-4.91v9.273H1.636A1.636 1.636 0 0 1 0 19.366V5.457c0-2.023 2.309-3.178 3.927-1.964L5.455 4.64 12 9.548l6.545-4.91 1.528-1.145C21.69 2.28 24 3.434 24 5.457Z' fill='#EA4335' />
    </svg>
  )
}

function JiraIntLogo() {
  return (
    <svg width='22' height='22' viewBox='0 0 24 24' fill='none' aria-hidden='true'>
      <path d='M11.53 2L2 11.53l4.2 4.2 5.33-5.33L16.73 5.3 11.53 2z' fill='#2684FF' />
      <path d='M11.53 22L21.06 12.47l-4.2-4.2-5.33 5.33L6.33 18.7l5.2 3.3z' fill='#2684FF' />
    </svg>
  )
}

function HubSpotIntLogo() {
  return (
    <svg width='22' height='22' viewBox='0 0 24 24' fill='none' aria-hidden='true'>
      <circle cx='12' cy='12' r='12' fill='#FF7A59' />
      <path d='M9 8.5V13a3 3 0 1 0 6 0v-.5' stroke='white' strokeWidth='2' strokeLinecap='round' />
      <circle cx='15' cy='8.5' r='2' fill='white' />
    </svg>
  )
}

function FigmaIntLogo() {
  return (
    <svg width='22' height='22' viewBox='0 0 24 24' fill='none' aria-hidden='true'>
      <path d='M8 24c2.2 0 4-1.8 4-4v-4H8c-2.2 0-4 1.8-4 4s1.8 4 4 4z' fill='#0ACF83' />
      <path d='M4 12c0-2.2 1.8-4 4-4h4v8H8c-2.2 0-4-1.8-4-4z' fill='#A259FF' />
      <path d='M4 4c0-2.2 1.8-4 4-4h4v8H8C5.8 8 4 6.2 4 4z' fill='#F24E1E' />
      <path d='M12 0h4c2.2 0 4 1.8 4 4s-1.8 4-4 4h-4V0z' fill='#FF7262' />
      <circle cx='16' cy='12' r='4' fill='#1ABCFE' />
    </svg>
  )
}

// ─── Provider marquee ─────────────────────────────────────────────────────────

function ProviderMarquee() {
  // Duplicate items to create seamless loop
  const items = [...PROVIDER_HIGHLIGHTS, ...PROVIDER_HIGHLIGHTS]

  return (
    <div className='relative overflow-hidden'>
      {/* Left blur mask */}
      <div className='pointer-events-none absolute inset-y-0 left-0 z-10 w-24 bg-gradient-to-r from-[#070b12] to-transparent' />
      {/* Right blur mask */}
      <div className='pointer-events-none absolute inset-y-0 right-0 z-10 w-24 bg-gradient-to-l from-[#070b12] to-transparent' />
      <div
        className='flex gap-3 py-4 animate-marquee'
        style={{ width: 'max-content' }}
      >
        {items.map((ph, i) => {
          const provider = PROVIDERS.find((p) => p.id === ph.id)
          return (
            <article
              key={`${ph.id}-${i}`}
              className='flex shrink-0 items-center gap-3 rounded-2xl border border-white/8 bg-[#0c1018] px-5 py-3'
            >
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
    </div>
  )
}

// ─── Glass integrations modal ─────────────────────────────────────────────────

function IntegrationsModal() {
  const orbitItems = INTEGRATIONS
  const centerSize = 90
  const orbitR1 = 100
  const orbitR2 = 160
  const cx = 200
  const cy = 190

  return (
    <div className='relative mx-auto flex max-w-sm items-center justify-center'>
      {/* Glass file card */}
      <div
        className='relative overflow-hidden rounded-[32px] border border-white/10 bg-white/5 px-8 py-10 shadow-2xl backdrop-blur-xl'
        style={{ minWidth: 340, minHeight: 380 }}
      >
        {/* Subtle inner glow */}
        <div className='pointer-events-none absolute inset-0 rounded-[32px] bg-gradient-to-br from-cyan-400/8 via-transparent to-blue-500/6' />

        {/* SVG illustration: logos as circles orbiting and falling into center file icon */}
        <svg
          viewBox={`0 0 ${cx * 2} ${cy * 2 + 10}`}
          className='w-full'
          aria-hidden='true'
        >
          {/* Center file icon */}
          <g transform={`translate(${cx - centerSize / 2}, ${cy - centerSize / 2})`}>
            <rect width={centerSize} height={centerSize} rx='18' fill='rgba(34,211,238,0.08)' stroke='rgba(34,211,238,0.25)' strokeWidth='1.5' />
            {/* Aegis shield centered */}
            <g transform={`translate(${centerSize / 2 - 16}, ${centerSize / 2 - 16})`}>
              <AegisShieldLogo size={32} />
            </g>
            {/* Falling circle effect: small circles dropping into center */}
            <circle cx={centerSize / 2} cy={-12} r='5' fill='rgba(34,211,238,0.4)' className='animate-fall-1' />
            <circle cx={centerSize / 2 - 18} cy={-24} r='4' fill='rgba(56,189,248,0.35)' className='animate-fall-2' />
            <circle cx={centerSize / 2 + 16} cy={-20} r='3.5' fill='rgba(99,102,241,0.4)' className='animate-fall-3' />
          </g>

          {/* Inner orbit ring (subtle) */}
          <circle cx={cx} cy={cy} r={orbitR1} stroke='rgba(255,255,255,0.04)' strokeWidth='1' fill='none' strokeDasharray='4 6' />
          {/* Outer orbit ring */}
          <circle cx={cx} cy={cy} r={orbitR2} stroke='rgba(255,255,255,0.03)' strokeWidth='1' fill='none' strokeDasharray='4 8' />

          {/* Inner orbit logos (6) */}
          {orbitItems.slice(0, 6).map((item, i) => {
            const angle = (i / 6) * 2 * Math.PI - Math.PI / 2
            const x = cx + orbitR1 * Math.cos(angle)
            const y = cy + orbitR1 * Math.sin(angle)
            return (
              <foreignObject key={item.name} x={x - 16} y={y - 16} width='32' height='32'>
                <div
                  className='flex h-8 w-8 items-center justify-center rounded-full border border-white/10 bg-[#111] shadow-lg'
                  title={item.name}
                >
                  <div className='scale-[0.7]'>{item.logo}</div>
                </div>
              </foreignObject>
            )
          })}

          {/* Outer orbit logos (remaining) */}
          {orbitItems.slice(6).map((item, i) => {
            const angle = (i / 6) * 2 * Math.PI - Math.PI / 4
            const x = cx + orbitR2 * Math.cos(angle)
            const y = cy + orbitR2 * Math.sin(angle)
            return (
              <foreignObject key={item.name} x={x - 16} y={y - 16} width='32' height='32'>
                <div
                  className='flex h-8 w-8 items-center justify-center rounded-full border border-white/10 bg-[#111] shadow-lg'
                  title={item.name}
                >
                  <div className='scale-[0.7]'>{item.logo}</div>
                </div>
              </foreignObject>
            )
          })}
        </svg>

        {/* Integration names below */}
        <div className='mt-4 flex flex-wrap justify-center gap-2'>
          {INTEGRATIONS.map((item) => (
            <span
              key={item.name}
              className='rounded-full border border-white/8 bg-white/4 px-3 py-1 text-[11px] text-zinc-400'
            >
              {item.name}
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}

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
                Aegis browses, codes, researches, files PRs, sends messages, and schedules recurring tasks. End to end, without you switching tabs. Give it a task. Get back a result.
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

      {/* ── PROVIDER MARQUEE ─────────────────────────────────────────────── */}
      <section className='w-full py-4 sm:py-6'>
        <ProviderMarquee />
      </section>

      {/* ── FEATURES / CAPABILITY MAP ────────────────────────────────────── */}
      <section id='features' className='mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 sm:py-18'>
        <Reveal className='mb-10 max-w-2xl'>
          <p className='text-[11px] uppercase tracking-[0.24em] text-cyan-200'>Aegis features and capabilities</p>
          <h2 className='mt-4 text-2xl font-semibold text-white sm:text-3xl md:text-4xl'>
            Everything you need to move from instruction to shipped output.
          </h2>
          <p className='mt-4 text-sm leading-7 text-zinc-400'>
            Aegis combines browser automation, code execution, persistent memory, scheduled automations, and multi-agent orchestration in a single operator surface so nothing falls through the gap between tools.
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
                {/* Icon pill with title inside */}
                <div className='flex items-center gap-3 rounded-2xl border border-cyan-400/20 bg-cyan-400/8 px-4 py-3 text-cyan-200'>
                  {feature.icon({ className: 'h-5 w-5 shrink-0' })}
                  <span className='text-sm font-semibold text-white'>{feature.title}</span>
                </div>
                <p className='mt-4 text-sm leading-7 text-zinc-300'>{feature.description}</p>
              </article>
            </Reveal>
          ))}
        </div>
      </section>

      {/* ── WHY YOU MUST SHIFT — COMPARISON ──────────────────────────────── */}
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
          {COMPARISONS.map((comp, index) => (
            <Reveal key={comp.task} delayMs={revealDelay(index, 80)}>
              <div className='overflow-hidden rounded-[24px] border border-white/8 bg-[#0c1018]'>
                <p className='border-b border-white/6 px-6 py-3 text-[10px] uppercase tracking-[0.22em] text-zinc-500'>
                  {comp.task}
                </p>
                <div className='grid gap-0 sm:grid-cols-2'>
                  {/* Competitor row */}
                  <div className='flex items-center gap-3 border-b border-white/6 px-6 py-4 sm:border-b-0 sm:border-r'>
                    <span className='inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[#1a1a1a]'>
                      {comp.competitorLogo}
                    </span>
                    <span className='shrink-0 text-xs font-medium text-zinc-500'>{comp.competitor}</span>
                    <p className='text-sm text-zinc-300'>{comp.competitorAction}</p>
                  </div>
                  {/* Aegis row */}
                  <div className='flex items-center gap-3 bg-cyan-400/4 px-6 py-4'>
                    <span className='inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[#1a1a1a]'>
                      <AegisShieldLogo size={20} />
                    </span>
                    <span className='shrink-0 rounded-full bg-cyan-500/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-cyan-300'>
                      Aegis
                    </span>
                    <p className='text-sm font-medium text-white'>{comp.aegisAction}</p>
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
                  One instruction. Aegis browses, researches, codes, files the PR, and sends the Slack update. You review the result. You don't do the work.
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
              {/* Screenshot placeholder */}
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

      {/* ── INTEGRATIONS AND MESSAGING ───────────────────────────────────── */}
      <section id='integrations' className='mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 sm:py-18'>
        <Reveal className='mb-10 max-w-2xl'>
          <p className='text-[11px] uppercase tracking-[0.24em] text-cyan-200'>Integrations and messaging</p>
          <h2 className='mt-4 text-2xl font-semibold text-white sm:text-3xl md:text-4xl'>
            Aegis connects to the tools your team already uses.
          </h2>
        </Reveal>
        <div className='grid gap-10 lg:grid-cols-2 lg:items-center'>
          <Reveal>
            <IntegrationsModal />
          </Reveal>
          <Reveal delayMs={100} className='flex flex-col gap-6'>
            <p className='text-base leading-8 text-zinc-300'>
              Aegis operates like a human coworker. It opens apps, reads data, takes actions, and reports back, using the same tools your team uses every day. No middleware. No Zapier. No glue code.
            </p>
            <p className='text-base leading-8 text-zinc-300'>
              Connect Aegis to GitHub, Slack, Google Drive, Linear, Notion, Stripe, and more. It navigates your actual interfaces the same way a person would.
            </p>
            <div className='rounded-[20px] border border-cyan-400/15 bg-cyan-400/5 p-5'>
              <p className='text-sm font-semibold text-white'>Talk to Aegis through your favorite work platform</p>
              <p className='mt-2 text-sm leading-7 text-zinc-400'>
                Deploy Aegis as a bot on Telegram, Slack, or Discord. Assign tasks in a message, get results back in the same thread. Your team never leaves the tools they already live in.
              </p>
              <div className='mt-4 flex items-center gap-4'>
                <span className='inline-flex items-center gap-2 rounded-full border border-white/8 bg-[#1a1a1a] px-3 py-1.5 text-xs text-zinc-300'>
                  <TelegramIntLogo />
                  Telegram
                </span>
                <span className='inline-flex items-center gap-2 rounded-full border border-white/8 bg-[#1a1a1a] px-3 py-1.5 text-xs text-zinc-300'>
                  <SlackIntLogo />
                  Slack
                </span>
                <span className='inline-flex items-center gap-2 rounded-full border border-white/8 bg-[#1a1a1a] px-3 py-1.5 text-xs text-zinc-300'>
                  <DiscordIntLogo />
                  Discord
                </span>
              </div>
            </div>
          </Reveal>
        </div>
      </section>

      {/* ── USE CASES ────────────────────────────────────────────────────── */}
      <section id='use-cases' className='mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 sm:py-18'>
        <Reveal className='mb-8 max-w-2xl'>
          <p className='text-[11px] uppercase tracking-[0.24em] text-cyan-200'>Use cases</p>
          <h2 className='mt-4 text-2xl font-semibold text-white sm:text-3xl md:text-4xl'>
            What Aegis can own for your team.
          </h2>
          <p className='mt-4 text-sm leading-7 text-zinc-400'>
            Click any workflow to see exactly how Aegis handles it, with prompts you can run right now.
          </p>
        </Reveal>

        <div className='grid gap-4 lg:grid-cols-2'>
          {USE_CASE_ROWS.map((row, rIndex) => (
            <Reveal key={row.category} delayMs={revealDelay(rIndex, 80)}>
              <div className='overflow-hidden rounded-[24px] border border-white/8 bg-[#0c1018]'>
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
