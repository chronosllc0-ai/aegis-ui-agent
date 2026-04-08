import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiRequest } from '../lib/api'

export type InstalledSkill = {
  skill_id: string
  slug: string
  name: string
  version_id: string
  enabled: boolean
  publish_target?: string
  risk_label?: string
  updated_at?: string
}

export type HubSkill = {
  id: string
  slug: string
  name: string
  description: string
  publish_target?: string
  risk_label?: string
  updated_at?: string
  owner?: {
    name?: string | null
    username?: string | null
    avatar_url?: string | null
  }
}

export type SkillSubmission = {
  id: string
  review_state: string
}

export type AdminSkillsPolicy = {
  allow_unreviewed_installs: boolean
  block_high_risk_skills: boolean
  require_approval_before_install: boolean
  default_enabled_skill_ids: string[]
}

export type AdminSkillQueueItem = {
  submission: {
    id: string
    skill_id: string
    review_state: string
    created_at?: string
  }
  skill: {
    id: string
    slug: string
    name: string
    status: string
    publish_target: string
    risk_label?: string
  }
  version: {
    id: string
    version?: number
    metadata_json?: Record<string, unknown>
  }
}

const DEFAULT_POLICY: AdminSkillsPolicy = {
  allow_unreviewed_installs: false,
  block_high_risk_skills: true,
  require_approval_before_install: false,
  default_enabled_skill_ids: [],
}

export function useSkills(isAdmin: boolean) {
  const [installed, setInstalled] = useState<InstalledSkill[]>([])
  const [hubSkills, setHubSkills] = useState<HubSkill[]>([])
  const [policy, setPolicy] = useState<AdminSkillsPolicy>(DEFAULT_POLICY)
  const [reviewQueue, setReviewQueue] = useState<AdminSkillQueueItem[]>([])
  const [loadingInstalled, setLoadingInstalled] = useState(true)
  const [loadingHub, setLoadingHub] = useState(true)
  const [loadingPolicy, setLoadingPolicy] = useState(isAdmin)
  const [loadingQueue, setLoadingQueue] = useState(isAdmin)

  const refreshInstalled = useCallback(async () => {
    setLoadingInstalled(true)
    try {
      const data = await apiRequest<{ skills?: InstalledSkill[] }>('/api/skills/installed')
      setInstalled(Array.isArray(data.skills) ? data.skills : [])
    } finally {
      setLoadingInstalled(false)
    }
  }, [])

  const refreshHub = useCallback(async () => {
    setLoadingHub(true)
    try {
      const data = await apiRequest<{ skills?: HubSkill[] }>('/api/skills/hub')
      setHubSkills(Array.isArray(data.skills) ? data.skills : [])
    } finally {
      setLoadingHub(false)
    }
  }, [])

  const refreshPolicy = useCallback(async () => {
    if (!isAdmin) return
    setLoadingPolicy(true)
    try {
      const data = await apiRequest<{ policy?: Partial<AdminSkillsPolicy> }>('/api/admin/skills/policy')
      setPolicy({ ...DEFAULT_POLICY, ...(data.policy ?? {}) })
    } finally {
      setLoadingPolicy(false)
    }
  }, [isAdmin])

  const refreshReviewQueue = useCallback(async () => {
    if (!isAdmin) return
    setLoadingQueue(true)
    try {
      const data = await apiRequest<{ items?: AdminSkillQueueItem[] }>('/api/admin/skills/review-queue')
      setReviewQueue(Array.isArray(data.items) ? data.items : [])
    } finally {
      setLoadingQueue(false)
    }
  }, [isAdmin])

  useEffect(() => {
    void refreshInstalled()
    void refreshHub()
  }, [refreshInstalled, refreshHub])

  useEffect(() => {
    if (!isAdmin) return
    void refreshPolicy()
    void refreshReviewQueue()
  }, [isAdmin, refreshPolicy, refreshReviewQueue])

  const toggleSkill = useCallback(async (skillId: string, enabled: boolean) => {
    await apiRequest('/api/skills/toggle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ skill_id: skillId, enabled }),
    })
  }, [])

  const uninstallSkill = useCallback(async (skillId: string) => {
    await apiRequest(`/api/skills/${encodeURIComponent(skillId)}`, { method: 'DELETE' })
  }, [])

  const installSkill = useCallback(async (skillId: string) => {
    await apiRequest(`/api/skills/${encodeURIComponent(skillId)}/install`, { method: 'POST' })
  }, [])

  const submitSkill = useCallback(
    async (payload: {
      slug: string
      name: string
      description: string
      publish_target: 'hub' | 'global'
      metadata_json: Record<string, unknown>
      skill_md: string
      workflow_action: 'save_draft' | 'submit_review'
    }): Promise<SkillSubmission> => {
      const data = await apiRequest<{ submission: SkillSubmission }>('/api/skills/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      return data.submission
    },
    [],
  )

  const savePolicy = useCallback(async (nextPolicy: AdminSkillsPolicy) => {
    try {
      const data = await apiRequest<{ policy?: Partial<AdminSkillsPolicy> }>('/api/admin/skills/policy', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(nextPolicy),
      })
      setPolicy({ ...DEFAULT_POLICY, ...nextPolicy, ...(data.policy ?? {}) })
    } catch (error) {
      // Keep previous state untouched on failure so UI never drifts from persisted policy.
      throw error
    }
  }, [])

  const reviewSubmission = useCallback(async (submissionId: string, decision: 'approve_hub' | 'approve_global' | 'reject' | 'needs_changes', notes?: string) => {
    await apiRequest(`/api/admin/skills/${encodeURIComponent(submissionId)}/review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision, notes }),
    })
  }, [])

  const scanSubmission = useCallback(async (submissionId: string) => {
    await apiRequest(`/api/admin/skills/${encodeURIComponent(submissionId)}/scan`, { method: 'POST' })
  }, [])

  const installedMap = useMemo(() => new Map(installed.map((skill) => [skill.skill_id, skill])), [installed])

  return {
    installed,
    installedMap,
    setInstalled,
    loadingInstalled,
    refreshInstalled,
    toggleSkill,
    uninstallSkill,
    installSkill,
    hubSkills,
    loadingHub,
    refreshHub,
    submitSkill,
    policy,
    loadingPolicy,
    refreshPolicy,
    savePolicy,
    reviewQueue,
    loadingQueue,
    refreshReviewQueue,
    reviewSubmission,
    scanSubmission,
  }
}
