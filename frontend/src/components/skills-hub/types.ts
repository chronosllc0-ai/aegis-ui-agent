export type HubState =
  | 'draft'
  | 'submitted'
  | 'under_review'
  | 'changes_requested'
  | 'approved'
  | 'published'
  | 'suspended'
  | 'archived'
  | 'rejected'

export type HubTransition = {
  id: string
  from_state: HubState
  to_state: HubState
  actor_id: string
  actor_role: string
  notes?: string | null
  created_at: string
}

export type HubSubmission = {
  id: string
  skill_id?: string | null
  skill_slug: string
  title: string
  description: string
  risk_label: string
  revision: number
  submitted_by: string
  current_state: HubState
  reviewer_notes: string[]
  created_at: string
  updated_at?: string | null
  history: HubTransition[]
}

export const HUB_BADGE: Record<HubState, string> = {
  draft: 'border-zinc-500/30 bg-zinc-500/10 text-zinc-300',
  submitted: 'border-cyan-500/30 bg-cyan-500/10 text-cyan-300',
  under_review: 'border-amber-500/30 bg-amber-500/10 text-amber-300',
  changes_requested: 'border-orange-500/30 bg-orange-500/10 text-orange-300',
  approved: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
  published: 'border-blue-500/30 bg-blue-500/10 text-blue-300',
  suspended: 'border-fuchsia-500/30 bg-fuchsia-500/10 text-fuchsia-300',
  archived: 'border-zinc-600/30 bg-zinc-600/10 text-zinc-400',
  rejected: 'border-red-500/30 bg-red-500/10 text-red-300',
}
