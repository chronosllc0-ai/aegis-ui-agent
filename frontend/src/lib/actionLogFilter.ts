import type { LogEntry } from '../hooks/useWebSocket'

export const BROWSER_PRIMITIVE_TOOLS = new Set([
  'click', 'click_element', 'left_click', 'right_click', 'double_click',
  'type_text', 'type', 'input_text', 'fill_input', 'clear_and_type',
  'scroll', 'scroll_page', 'scroll_down', 'scroll_up',
  'wait', 'wait_for_element', 'wait_for_selector',
  'screenshot', 'take_screenshot',
  'go_to_url', 'navigate', 'open_url', 'load_url',
  'go_back',
])

const EXCLUDED_TYPES: ReadonlySet<LogEntry['type']> = new Set([
  'result',
  'error',
  'interrupt',
  'reasoning',
  'reasoning_start',
])

export function extractToolName(message: string): string | null {
  const toolMatch = message.match(/^\[([\w_]+)\]/)
  return toolMatch?.[1]?.toLowerCase() ?? null
}

export function isBrowserPrimitiveActionLogEntry(entry: LogEntry): boolean {
  if (EXCLUDED_TYPES.has(entry.type)) return false

  // Keep chat-origin navigate rows out of the Action Log.
  if (entry.taskId && entry.elapsedSeconds === 0 && entry.stepKind === 'navigate') return false

  const toolName = extractToolName(entry.message)
  if (!toolName) return false

  return BROWSER_PRIMITIVE_TOOLS.has(toolName)
}
