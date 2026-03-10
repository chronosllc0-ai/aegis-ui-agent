import type { LogEntry, WorkflowStep } from '../hooks/useWebSocket'
import type { WorkflowTemplate } from '../hooks/useSettings'

export type TaskHistoryItem = {
  id: string
  title: string
  dateLabel: string
  instruction: string
}

export const DEMO_TASKS: TaskHistoryItem[] = [
  { id: 'task-001', title: 'Summarize Telegram updates', dateLabel: 'Today', instruction: 'Read latest Telegram messages and summarize key points' },
  { id: 'task-002', title: 'Post screenshot to Discord', dateLabel: 'Today', instruction: 'Send my latest screenshot to #shipping-room' },
  { id: 'task-003', title: 'Research AI browser agents', dateLabel: 'Yesterday', instruction: 'Search latest AI UI navigator launches and compare' },
]

export const DEMO_LOGS: LogEntry[] = [
  { id: 'l1', taskId: 'task-001', message: 'Read latest Telegram messages and summarize key points', type: 'step', status: 'in_progress', timestamp: '10:12:01', stepKind: 'navigate', elapsedSeconds: 0 },
  { id: 'l2', taskId: 'task-001', message: 'Opened Telegram integration and listed recent chats', type: 'step', status: 'completed', timestamp: '10:12:04', stepKind: 'analyze', elapsedSeconds: 2.8 },
  { id: 'l3', taskId: 'task-001', message: 'Fetched 8 messages from product-updates', type: 'step', status: 'completed', timestamp: '10:12:08', stepKind: 'other', elapsedSeconds: 3.3 },
  { id: 'l4', taskId: 'task-001', message: 'Task completed', type: 'result', status: 'completed', timestamp: '10:12:12', stepKind: 'other', elapsedSeconds: 1.7 },
  { id: 'l5', taskId: 'task-002', message: 'Send latest screenshot to Discord #shipping-room', type: 'step', status: 'steered', timestamp: '11:03:12', stepKind: 'navigate', elapsedSeconds: 0.0 },
  { id: 'l6', taskId: 'task-002', message: 'Uploaded screenshot attachment and sent message', type: 'result', status: 'completed', timestamp: '11:03:21', stepKind: 'other', elapsedSeconds: 9.1 },
]

export const DEMO_WORKFLOW_STEPS: WorkflowStep[] = [
  { step_id: 'w1', parent_step_id: null, action: 'navigate', description: 'Open Telegram workspace', status: 'completed', timestamp: '2026-03-10T10:12:02Z', duration_ms: 1100, screenshot: null },
  { step_id: 'w2', parent_step_id: 'w1', action: 'telegram_list_chats', description: 'List available chats', status: 'completed', timestamp: '2026-03-10T10:12:04Z', duration_ms: 740, screenshot: null },
  { step_id: 'w3', parent_step_id: 'w2', action: 'telegram_get_messages', description: 'Read latest 8 messages from product-updates', status: 'completed', timestamp: '2026-03-10T10:12:07Z', duration_ms: 1220, screenshot: null },
  { step_id: 'w4', parent_step_id: 'w3', action: 'summarize', description: 'Generate concise summary with risks and blockers', status: 'completed', timestamp: '2026-03-10T10:12:10Z', duration_ms: 920, screenshot: null },
]

export const DEMO_WORKFLOW_TEMPLATES: WorkflowTemplate[] = [
  { id: 'wf-1', name: 'Telegram Daily Summary', instruction: 'Read my latest Telegram messages and summarize', stepCount: 4, lastRunAt: '2026-03-10T10:12:12Z' },
  { id: 'wf-2', name: 'Share screenshot to Discord', instruction: 'Post my latest screenshot to Discord channel', stepCount: 3, lastRunAt: '2026-03-09T20:43:05Z' },
]
