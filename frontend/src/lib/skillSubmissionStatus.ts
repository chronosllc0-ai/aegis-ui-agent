export const SKILL_SUBMISSION_STATUSES = [
  'draft',
  'submitted',
  'scanning',
  'review',
  'approved',
  'rejected',
  'published_global',
  'published_hub',
] as const

export type SkillSubmissionStatus = (typeof SKILL_SUBMISSION_STATUSES)[number]

export type SkillStatusBadge = {
  label: string
  className: string
}

const BADGE_BY_STATUS: Record<SkillSubmissionStatus, SkillStatusBadge> = {
  draft: { label: 'Draft', className: 'bg-zinc-500/10 text-zinc-300 border-zinc-500/20' },
  submitted: { label: 'Submitted', className: 'bg-cyan-500/10 text-cyan-300 border-cyan-500/20' },
  scanning: { label: 'Scanning', className: 'bg-indigo-500/10 text-indigo-300 border-indigo-500/20' },
  review: { label: 'In Review', className: 'bg-amber-500/10 text-amber-300 border-amber-500/20' },
  approved: { label: 'Approved', className: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/20' },
  rejected: { label: 'Rejected', className: 'bg-red-500/10 text-red-300 border-red-500/20' },
  published_global: { label: 'Published (Global)', className: 'bg-violet-500/10 text-violet-300 border-violet-500/20' },
  published_hub: { label: 'Published (Hub)', className: 'bg-blue-500/10 text-blue-300 border-blue-500/20' },
}

export function normalizeSkillSubmissionStatus(status: string): SkillSubmissionStatus {
  if (status === 'published_global' || status === 'published_hub') return status
  if (status === 'rejected' || status === 'draft' || status === 'submitted' || status === 'scanning' || status === 'review') {
    return status
  }
  // Backward-compat mapping for legacy states
  if (status === 'approved_global') return 'published_global'
  if (status === 'approved_hub') return 'published_hub'
  if (status === 'pending_scan' || status === 'pending_policy') return 'scanning'
  if (status === 'pending_review') return 'review'
  if (status === 'needs_changes') return 'draft'
  return 'approved'
}

export function getSkillStatusBadge(status: string): SkillStatusBadge {
  const normalized = normalizeSkillSubmissionStatus(status)
  return BADGE_BY_STATUS[normalized]
}

export function filterSkillsByStatus<T extends { status: string }>(items: T[], statusFilter: SkillSubmissionStatus | 'all'): T[] {
  if (statusFilter === 'all') return items
  return items.filter((item) => normalizeSkillSubmissionStatus(item.status) === statusFilter)
}
