export const AGENT_MODE_IDS = ['orchestrator', 'planner', 'architect', 'deep_research', 'code'] as const

export type AgentModeId = (typeof AGENT_MODE_IDS)[number]

export type AgentModeOption = {
  id: AgentModeId
  label: string
  description: string
}

export const AGENT_MODES: AgentModeOption[] = [
  {
    id: 'orchestrator',
    label: 'Orchestrator',
    description: 'Routes work to specialist modes and synthesizes the final response.',
  },
  {
    id: 'planner',
    label: 'Planner',
    description: 'Builds structured plans and sequencing without executing tools.',
  },
  {
    id: 'architect',
    label: 'Architect',
    description: 'Designs systems, tradeoffs, and technical specs in read-only mode.',
  },
  {
    id: 'deep_research',
    label: 'Deep Research',
    description: 'Produces evidence-backed analysis from available context and sources.',
  },
  {
    id: 'code',
    label: 'Code',
    description: 'Execution mode: can use implementation tools and spawn subagents.',
  },
]

export const DEFAULT_AGENT_MODE: AgentModeId = 'orchestrator'
export const MODE_RUNTIME_SCHEMA_VERSION = '1.0' as const

export const MODE_RUNTIME_EVENT_NAMES = [
  'route_decision',
  'mode_transition',
  'worker_summary',
  'final_synthesis',
] as const

export type ModeRuntimeEventName = (typeof MODE_RUNTIME_EVENT_NAMES)[number]

type ModeRuntimeEventBase = {
  schema_version: typeof MODE_RUNTIME_SCHEMA_VERSION
  event_name: ModeRuntimeEventName
}

export type RouteDecisionEvent = ModeRuntimeEventBase & {
  event_name: 'route_decision'
  payload: {
    router_mode: AgentModeId
    selected_mode: AgentModeId
    reason: string
    confidence: number
    bypass_attempt_detected: boolean
    timeout_seconds: number
  }
}

export type ModeTransitionEvent = ModeRuntimeEventBase & {
  event_name: 'mode_transition'
  payload: {
    from_mode: AgentModeId
    to_mode: AgentModeId
    reason: string
    error?: string
  }
}

export type WorkerSummaryEvent = ModeRuntimeEventBase & {
  event_name: 'worker_summary'
  payload: {
    worker_mode: AgentModeId
    status: string
    summary: string
    fallback?: boolean
  }
}

export type FinalSynthesisEvent = ModeRuntimeEventBase & {
  event_name: 'final_synthesis'
  payload: {
    status: string
    synthesis: string
    child_results: Array<{ ref: string; mode: AgentModeId; status?: string }>
  }
}

export type ModeRuntimeEvent = RouteDecisionEvent | ModeTransitionEvent | WorkerSummaryEvent | FinalSynthesisEvent

export type ModeRuntimeEventParseFailure = {
  ok: false
  error: string
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

export function parseModeRuntimeEvent(input: unknown): { ok: true; event: ModeRuntimeEvent } | ModeRuntimeEventParseFailure {
  if (!isRecord(input)) return { ok: false, error: 'event_not_object' }
  const schemaVersion = String(input.schema_version ?? '')
  const eventName = String(input.event_name ?? '')
  const payload = input.payload
  if (schemaVersion !== MODE_RUNTIME_SCHEMA_VERSION) return { ok: false, error: `unsupported_schema_version:${schemaVersion || 'empty'}` }
  if (!(MODE_RUNTIME_EVENT_NAMES as readonly string[]).includes(eventName)) return { ok: false, error: `unknown_event_name:${eventName || 'empty'}` }
  if (!isRecord(payload)) return { ok: false, error: 'invalid_payload' }
  return { ok: true, event: input as ModeRuntimeEvent }
}

export function modeLabel(mode: unknown): string {
  const normalized = normalizeAgentMode(mode)
  return AGENT_MODES.find((item) => item.id === normalized)?.label ?? normalized
}

export function normalizeAgentMode(value: unknown): AgentModeId {
  const candidate = String(value ?? '').trim().toLowerCase()
  return (AGENT_MODE_IDS as readonly string[]).includes(candidate)
    ? (candidate as AgentModeId)
    : DEFAULT_AGENT_MODE
}
