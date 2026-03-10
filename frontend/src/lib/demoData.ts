import type { WorkflowTemplate } from '../hooks/useSettings'
import type { LogEntry, WorkflowStep } from '../hooks/useWebSocket'

export type TaskHistoryItem = {
  id: string
  title: string
  dateLabel: string
  instruction: string
  summary: string
}

export const DEMO_TASKS: TaskHistoryItem[] = [
  {
    id: 'task-001',
    title: 'Telegram Standup Summary',
    dateLabel: 'Today',
    instruction: 'Read latest Telegram messages and summarize key points for standup.',
    summary: '8 messages summarized, 2 blockers surfaced.',
  },
  {
    id: 'task-002',
    title: 'Post QA screenshot to Discord',
    dateLabel: 'Today',
    instruction: 'Send my latest screenshot to #shipping-room with release note.',
    summary: 'Screenshot shared to channel with changelog context.',
  },
  {
    id: 'task-003',
    title: 'Slack channel pulse check',
    dateLabel: 'Yesterday',
    instruction: 'Fetch latest #design channel updates and identify decisions.',
    summary: 'Detected 3 action items and 1 open question.',
  },
  {
    id: 'task-004',
    title: 'AI Navigator competitor scan',
    dateLabel: 'Yesterday',
    instruction: 'Search for AI browser agent launches and compare features.',
    summary: 'Compared 5 products by multimodal strength and automation depth.',
  },
]

export const DEMO_LOGS: LogEntry[] = [
  { id: 'l1', taskId: 'task-001', message: 'Read latest Telegram messages and summarize key points for standup.', type: 'step', status: 'in_progress', timestamp: '10:12:01', stepKind: 'navigate', elapsedSeconds: 0 },
  { id: 'l2', taskId: 'task-001', message: 'Opened Telegram integration and listed available chats.', type: 'step', status: 'completed', timestamp: '10:12:04', stepKind: 'analyze', elapsedSeconds: 2.8 },
  { id: 'l3', taskId: 'task-001', message: 'Fetched 8 messages from product-updates and team-ops.', type: 'step', status: 'completed', timestamp: '10:12:08', stepKind: 'other', elapsedSeconds: 3.3 },
  { id: 'l4', taskId: 'task-001', message: 'Generated summary and highlighted blockers.', type: 'step', status: 'completed', timestamp: '10:12:11', stepKind: 'type', elapsedSeconds: 2.4 },
  { id: 'l5', taskId: 'task-001', message: 'Task completed', type: 'result', status: 'completed', timestamp: '10:12:13', stepKind: 'other', elapsedSeconds: 1.8 },
  { id: 'l6', taskId: 'task-002', message: 'Send latest screenshot to Discord #shipping-room', type: 'step', status: 'steered', timestamp: '11:03:12', stepKind: 'navigate', elapsedSeconds: 0.0 },
  { id: 'l7', taskId: 'task-002', message: 'Uploaded screenshot attachment and posted release note.', type: 'result', status: 'completed', timestamp: '11:03:21', stepKind: 'other', elapsedSeconds: 9.1 },
]

export const DEMO_WORKFLOW_STEPS: WorkflowStep[] = [
  { step_id: 'w1', parent_step_id: null, action: 'navigate', description: 'Open Telegram workspace', status: 'completed', timestamp: '2026-03-10T10:12:02Z', duration_ms: 1100, screenshot: null },
  { step_id: 'w2', parent_step_id: 'w1', action: 'telegram_list_chats', description: 'List available chats for user', status: 'completed', timestamp: '2026-03-10T10:12:04Z', duration_ms: 740, screenshot: null },
  { step_id: 'w3', parent_step_id: 'w2', action: 'telegram_get_messages', description: 'Read latest 8 messages from product-updates', status: 'completed', timestamp: '2026-03-10T10:12:07Z', duration_ms: 1220, screenshot: null },
  { step_id: 'w4', parent_step_id: 'w3', action: 'analyze', description: 'Extract blockers and decisions', status: 'completed', timestamp: '2026-03-10T10:12:10Z', duration_ms: 910, screenshot: null },
  { step_id: 'w5', parent_step_id: 'w4', action: 'compose', description: 'Create standup-ready summary', status: 'completed', timestamp: '2026-03-10T10:12:12Z', duration_ms: 860, screenshot: null },
  { step_id: 'w6', parent_step_id: 'w5', action: 'publish', description: 'Post summary to action log and user output', status: 'completed', timestamp: '2026-03-10T10:12:14Z', duration_ms: 610, screenshot: null },
]

export const DEMO_WORKFLOW_TEMPLATES: WorkflowTemplate[] = [
  {
    id: 'wf-1',
    name: 'Telegram Daily Summary',
    description: 'Read latest Telegram messages and produce a concise daily summary.',
    instruction: 'Read my latest Telegram messages and summarize key updates.',
    tags: ['messaging', 'summary', 'daily'],
    usesIntegrations: ['Telegram'],
    stepCount: 6,
    favorite: true,
    lastRunAt: '2026-03-10T10:12:14Z',
  },
  {
    id: 'wf-2',
    name: 'Release Screenshot Broadcast',
    description: 'Share latest screenshot to Discord and Slack with release notes.',
    instruction: 'Post my latest screenshot to Discord and Slack release channels.',
    tags: ['release', 'broadcast'],
    usesIntegrations: ['Discord', 'Slack'],
    stepCount: 5,
    favorite: false,
    lastRunAt: '2026-03-09T20:43:05Z',
  },
  {
    id: 'wf-3',
    name: 'Competitor Signal Scan',
    description: 'Search web for competitor launches and summarize differentiators.',
    instruction: 'Search for AI browser agent launches and compare capabilities.',
    tags: ['research', 'web-search'],
    usesIntegrations: ['Web Search'],
    stepCount: 7,
    favorite: false,
    lastRunAt: '2026-03-09T17:18:00Z',
  },
]

export const DEMO_AUTH_USER = {
  name: 'Avery Chen',
  email: 'avery@aegis.dev',
  avatarUrl: 'https://placehold.co/80x80/0f172a/ffffff?text=AC',
}

export const DEMO_FRAME = `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1280 720'>
<rect width='1280' height='720' fill='#0f172a'/>
<rect x='120' y='90' width='1040' height='72' rx='12' fill='#111827' stroke='#334155'/>
<rect x='150' y='116' width='320' height='20' rx='10' fill='#334155'/>
<rect x='120' y='190' width='1040' height='420' rx='16' fill='#111827' stroke='#475569'/>
<rect x='170' y='240' width='500' height='26' rx='8' fill='#1d4ed8'/>
<rect x='170' y='282' width='430' height='14' rx='7' fill='#475569'/>
<rect x='170' y='320' width='780' height='180' rx='12' fill='#0b1220' stroke='#334155'/>
<rect x='980' y='240' width='130' height='36' rx='10' fill='#22c55e'/>
<text x='1020' y='263' fill='white' font-size='14' font-family='Arial'>Publish</text>
<text x='170' y='215' fill='#94a3b8' font-size='12' font-family='Arial'>Demo frame · visualized browser output</text>
</svg>`)}`
