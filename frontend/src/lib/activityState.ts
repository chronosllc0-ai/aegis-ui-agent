import type { ActivityPhase, TaskActivity, WebSocketPayload } from '../hooks/useWebSocket'

const BROWSER_TOOL_NAMES = new Set([
  'click',
  'type',
  'type_text',
  'scroll',
  'go_to_url',
  'go_back',
  'wait',
  'screenshot',
  'extract_page',
])

const STALE_ACTIVITY_LABEL = 'Aegis is processing…'
const DEFAULT_ACTIVITY_LABEL = 'Aegis is working…'

export const DEFAULT_ACTIVITY_STALE_AFTER_MS = 12_000

export type ActivityState = TaskActivity & {
  lastEventAt: number
}

export type ActivitySelector = {
  activityStatusLabel: string
  activityDetail?: string
  isActivityVisible: boolean
}

function getToolNameFromStep(content: string): string | null {
  const match = content.trim().match(/^\[([\w_]+)\]/)
  return match?.[1]?.toLowerCase() ?? null
}

function inferActivityFromContent(content: string): Pick<ActivityState, 'phase' | 'detail'> {
  const normalized = content.trim().toLowerCase()
  const toolName = getToolNameFromStep(content)
  if (toolName) {
    if (toolName === 'thinking') return { phase: 'thinking', detail: content }
    if (BROWSER_TOOL_NAMES.has(toolName)) return { phase: 'browsing', detail: content }
    if (/(model response|assistant response|generating|drafting)/i.test(content)) return { phase: 'generating', detail: content }
    return { phase: 'calling_tool', detail: content }
  }
  if (/(model response|assistant response|generating|drafting)/i.test(content)) {
    return { phase: 'generating', detail: content }
  }
  if (/(thinking|reasoning|analyzing|planning)/i.test(normalized)) {
    return { phase: 'thinking', detail: content }
  }
  return { phase: 'calling_tool', detail: DEFAULT_ACTIVITY_LABEL }
}

function getLabelForPhase(phase: ActivityPhase): string {
  switch (phase) {
    case 'thinking':
      return 'Aegis is thinking…'
    case 'browsing':
      return 'Aegis is browsing…'
    case 'calling_tool':
      return 'Aegis is calling tools…'
    case 'generating':
      return 'Aegis is generating response…'
    default:
      return DEFAULT_ACTIVITY_LABEL
  }
}

export function createIdleActivityState(now = Date.now()): ActivityState {
  const iso = new Date(now).toISOString()
  return {
    phase: 'idle',
    detail: undefined,
    updatedAt: iso,
    lastEventAt: now,
  }
}

export function reduceActivityState(state: ActivityState, payload: WebSocketPayload, now = Date.now()): ActivityState {
  const timestamp = new Date(now).toISOString()

  if (payload.type === 'result' || payload.type === 'error' || payload.type === 'interrupt') {
    return {
      ...createIdleActivityState(now),
      updatedAt: timestamp,
    }
  }

  if (payload.type === 'reasoning_start') {
    return {
      ...state,
      phase: 'thinking',
      detail: 'reasoning_start',
      updatedAt: timestamp,
      lastEventAt: now,
    }
  }

  if (payload.type === 'reasoning_delta') {
    return {
      ...state,
      phase: 'thinking',
      detail: String(payload.data?.delta ?? 'reasoning_delta'),
      updatedAt: timestamp,
      lastEventAt: now,
    }
  }

  if (payload.type === 'step' || payload.type === 'tool-call') {
    const stepType = String(payload.data?.type ?? '').toLowerCase()
    const nonExecutionStepTypes = new Set(['queue', 'steer', 'config'])
    if (payload.type === 'step' && nonExecutionStepTypes.has(stepType)) {
      return {
        ...state,
        updatedAt: timestamp,
        lastEventAt: now,
      }
    }
    const content = String(payload.data?.content ?? payload.data?.type ?? 'Step update')
    const inferred = inferActivityFromContent(content)
    return {
      ...state,
      ...inferred,
      updatedAt: timestamp,
      lastEventAt: now,
    }
  }

  if (payload.type === 'reasoning') {
    return {
      ...state,
      phase: 'generating',
      detail: 'reasoning_completed',
      updatedAt: timestamp,
      lastEventAt: now,
    }
  }

  return state
}

export function selectActivityView(
  state: ActivityState,
  isWorking: boolean,
  now = Date.now(),
  staleAfterMs = DEFAULT_ACTIVITY_STALE_AFTER_MS,
): ActivitySelector {
  if (!isWorking || state.phase === 'idle') {
    return { activityStatusLabel: '', activityDetail: undefined, isActivityVisible: false }
  }

  const isStale = now - state.lastEventAt >= staleAfterMs
  if (isStale) {
    return {
      activityStatusLabel: STALE_ACTIVITY_LABEL,
      activityDetail: state.detail,
      isActivityVisible: true,
    }
  }

  return {
    activityStatusLabel: getLabelForPhase(state.phase),
    activityDetail: state.detail,
    isActivityVisible: true,
  }
}
