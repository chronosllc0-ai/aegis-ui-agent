import type { LogEntry } from '../hooks/useWebSocket'

const TOOL_CALL_RE = /^\[([\w_]+)\]/

const BROWSER_TOOL_NAMES = new Set([
  'navigate_browser', 'navigate', 'go_to_url', 'open_url', 'load_url',
  'extract_page', 'go_back', 'wait',
  'click_element', 'click', 'left_click', 'right_click', 'double_click',
  'type_text', 'type', 'input_text', 'fill_input', 'clear_and_type',
  'scroll_page', 'scroll', 'scroll_down', 'scroll_up', 'scroll_to_element',
  'hover_element', 'hover', 'mouse_move',
  'press_key', 'key_press', 'keyboard_press',
  'take_screenshot', 'screenshot',
  'extract_text', 'get_page_text', 'get_inner_text',
  'get_element', 'find_element', 'wait_for_element', 'wait_for_selector',
  'select_option', 'check_checkbox', 'uncheck_checkbox',
  'get_page_html', 'get_dom', 'evaluate_js', 'execute_script',
  'drag_and_drop', 'upload_file_to_browser',
])

const SILENT_TOOL_NAMES = new Set([
  'thinking', 'think', 'internal_think',
  'wait', 'sleep', 'pause', 'noop', 'no_op',
  'set_next_step', 'plan_step', 'record_thought',
])

const BROWSER_STATUS_PATTERNS: RegExp[] = [
  /^session settings updated/i,
  /^workflow step update/i,
  /^starting task:/i,
  /^task (completed|interrupted|failed)/i,
]

type BrowserEventContext = {
  message: string
  entry?: Pick<LogEntry, 'stepKind' | 'elapsedSeconds'>
}

/**
 * Returns true when a persisted chat message is a raw echo of a browser
 * primitive tool call, e.g. `[click] ...`, `[go_to_url] ...`, `[wait] ...`.
 *
 * Unlike `isBrowserOnlyEvent` this is intentionally narrow: it only matches a
 * bracketed tool-name prefix whose name is in the browser/silent tool sets.
 * It deliberately does NOT match status phrases like "Task completed" so that
 * legitimate assistant prose is never hidden during thread rehydration.
 */
export function isBracketedBrowserToolEcho(message: string): boolean {
  const trimmed = message.trim()
  const toolMatch = trimmed.match(TOOL_CALL_RE)
  const toolName = toolMatch?.[1]?.toLowerCase()
  if (!toolName) return false
  return BROWSER_TOOL_NAMES.has(toolName) || SILENT_TOOL_NAMES.has(toolName)
}

/**
 * Returns true when an event belongs exclusively to browser execution workflow
 * (Action Log) and should be excluded from chat timelines.
 */
export function isBrowserOnlyEvent({ message, entry }: BrowserEventContext): boolean {
  const normalized = message.trim()

  if (BROWSER_STATUS_PATTERNS.some((pattern) => pattern.test(normalized))) return true

  if (entry) {
    if (entry.stepKind === 'click' || entry.stepKind === 'type' || entry.stepKind === 'scroll') return true
    if (entry.stepKind === 'navigate' && entry.elapsedSeconds > 0) return true
  }

  const toolMatch = normalized.match(TOOL_CALL_RE)
  const toolName = toolMatch?.[1]?.toLowerCase()
  if (toolName && (BROWSER_TOOL_NAMES.has(toolName) || SILENT_TOOL_NAMES.has(toolName))) return true

  return false
}

