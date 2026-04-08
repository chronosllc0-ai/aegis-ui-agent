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

export type AdminSkillsPolicy = {
  allow_unreviewed_installs: boolean
  block_high_risk_skills: boolean
  require_approval_before_install: boolean
  default_enabled_skill_ids: string[]
}

const DEFAULT_POLICY: AdminSkillsPolicy = {
  allow_unreviewed_installs: false,
  block_high_risk_skills: false,
  require_approval_before_install: false,
  default_enabled_skill_ids: [],
}

export function useSkills(isAdmin: boolean) {
  const [installed, setInstalled] = useState<InstalledSkill[]>([])
  const [policy, setPolicy] = useState<AdminSkillsPolicy>(DEFAULT_POLICY)
  const [loadingInstalled, setLoadingInstalled] = useState(true)
  const [loadingPolicy, setLoadingPolicy] = useState(isAdmin)

  const refreshInstalled = useCallback(async () => {
      setLoadingInstalled(true)
    try {
      const data = await apiRequest<{ skills?: InstalledSkill[] }>('/api/skills/installed')
      setInstalled(Array.isArray(data.skills) ? data.skills : [])
    } finally {
      setLoadingInstalled(false)
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

  useEffect(() => {
    void refreshInstalled()
  }, [refreshInstalled])

  useEffect(() => {
    if (!isAdmin) return
    void refreshPolicy()
  }, [isAdmin, refreshPolicy])

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

  const savePolicy = useCallback(async (nextPolicy: AdminSkillsPolicy) => {
    const data = await apiRequest<{ policy?: Partial<AdminSkillsPolicy> }>('/api/admin/skills/policy', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(nextPolicy),
    })
    setPolicy({ ...DEFAULT_POLICY, ...nextPolicy, ...(data.policy ?? {}) })
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
    policy,
    loadingPolicy,
    refreshPolicy,
    savePolicy,
  }
}
