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

export function normalizeAgentMode(value: unknown): AgentModeId {
  const candidate = String(value ?? '').trim().toLowerCase()
  return (AGENT_MODE_IDS as readonly string[]).includes(candidate)
    ? (candidate as AgentModeId)
    : DEFAULT_AGENT_MODE
}
