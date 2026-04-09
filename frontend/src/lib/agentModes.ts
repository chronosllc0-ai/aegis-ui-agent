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
  const payloadValidationError = validateModeRuntimePayload(eventName as ModeRuntimeEventName, payload)
  if (payloadValidationError) return { ok: false, error: payloadValidationError }
  return { ok: true, event: input as ModeRuntimeEvent }
}

function hasStringValue(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0
}

function isAgentModeId(value: unknown): value is AgentModeId {
  return (AGENT_MODE_IDS as readonly string[]).includes(String(value ?? '').trim().toLowerCase())
}

function validateModeRuntimePayload(eventName: ModeRuntimeEventName, payload: Record<string, unknown>): string | null {
  if (eventName === 'route_decision') {
    if (String(payload.router_mode ?? '').trim() !== 'orchestrator') return 'invalid_payload:route_decision.router_mode'
    if (!isAgentModeId(payload.selected_mode) || payload.selected_mode === 'orchestrator') return 'invalid_payload:route_decision.selected_mode'
    if (!hasStringValue(payload.reason)) return 'invalid_payload:route_decision.reason'
    if (typeof payload.confidence !== 'number') return 'invalid_payload:route_decision.confidence'
    if (typeof payload.bypass_attempt_detected !== 'boolean') return 'invalid_payload:route_decision.bypass_attempt_detected'
    if (!Number.isInteger(payload.timeout_seconds)) return 'invalid_payload:route_decision.timeout_seconds'
    return null
  }
  if (eventName === 'mode_transition') {
    if (!isAgentModeId(payload.from_mode)) return 'invalid_payload:mode_transition.from_mode'
    if (!isAgentModeId(payload.to_mode)) return 'invalid_payload:mode_transition.to_mode'
    if (!hasStringValue(payload.reason)) return 'invalid_payload:mode_transition.reason'
    if (payload.error !== undefined && typeof payload.error !== 'string') return 'invalid_payload:mode_transition.error'
    return null
  }
  if (eventName === 'worker_summary') {
    if (!isAgentModeId(payload.worker_mode)) return 'invalid_payload:worker_summary.worker_mode'
    if (!hasStringValue(payload.status)) return 'invalid_payload:worker_summary.status'
    if (typeof payload.summary !== 'string') return 'invalid_payload:worker_summary.summary'
    if (payload.fallback !== undefined && typeof payload.fallback !== 'boolean') return 'invalid_payload:worker_summary.fallback'
    return null
  }
  if (eventName === 'final_synthesis') {
    if (!hasStringValue(payload.status)) return 'invalid_payload:final_synthesis.status'
    if (typeof payload.synthesis !== 'string') return 'invalid_payload:final_synthesis.synthesis'
    const childResults = payload.child_results
    if (!Array.isArray(childResults)) return 'invalid_payload:final_synthesis.child_results'
    for (const child of childResults) {
      if (!isRecord(child)) return 'invalid_payload:final_synthesis.child_results.item'
      if (!hasStringValue(child.ref)) return 'invalid_payload:final_synthesis.child_results.ref'
      if (!isAgentModeId(child.mode)) return 'invalid_payload:final_synthesis.child_results.mode'
      if (child.status !== undefined && typeof child.status !== 'string') return 'invalid_payload:final_synthesis.child_results.status'
    }
    return null
  }
  return 'invalid_payload:unsupported_event'
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
