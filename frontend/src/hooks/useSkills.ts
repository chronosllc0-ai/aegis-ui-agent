import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiUrl } from '../lib/api'

export type InstalledSkill = {
  skill_id: string
  slug: string
  name: string
  enabled: boolean
  version_id: string
  version?: number
  source?: string
  publish_target?: string
  risk_label?: string
  updated_at?: string
}

export type AdminSkillsPolicy = {
  allow_global_skills: boolean
  allow_hub_skills: boolean
  require_approval_before_install: boolean
  default_enabled_skill_ids: string[]
  updated_at?: string
  updated_by?: string | null
}

const DEFAULT_POLICY: AdminSkillsPolicy = {
  allow_global_skills: true,
  allow_hub_skills: true,
  require_approval_before_install: false,
  default_enabled_skill_ids: [],
}

async function readJson(response: Response): Promise<any> {
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(data?.detail ?? 'Request failed')
  }
  return data
}

export function useSkills(isAdmin: boolean) {
  const [installedSkills, setInstalledSkills] = useState<InstalledSkill[]>([])
  const [policy, setPolicy] = useState<AdminSkillsPolicy>(DEFAULT_POLICY)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const installedRes = await fetch(apiUrl('/api/skills/installed'), { credentials: 'include' })
      const installedData = await readJson(installedRes)
      setInstalledSkills(Array.isArray(installedData.skills) ? installedData.skills : [])

      if (isAdmin) {
        const policyRes = await fetch(apiUrl('/api/admin/skills/policy'), { credentials: 'include' })
        const policyData = await readJson(policyRes)
        setPolicy({ ...DEFAULT_POLICY, ...(policyData.policy ?? {}) })
      }
    } finally {
      setLoading(false)
    }
  }, [isAdmin])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const toggleSkill = useCallback(async (skillId: string, enabled: boolean) => {
    const previous = installedSkills
    setInstalledSkills((prev) => prev.map((skill) => (skill.skill_id === skillId ? { ...skill, enabled } : skill)))
    setInstalledSkills((prev) => prev.map((skill) => (skill.skill_id === skillId ? { ...skill, enabled } : skill)))
    try {
      const response = await fetch(apiUrl('/api/skills/toggle'), {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ skill_id: skillId, enabled }),
      })
      await readJson(response)
    } catch (error) {
      setInstalledSkills(previous)
      throw error
    }
  }, [installedSkills])

  const uninstallSkill = useCallback(async (skillId: string) => {
    const previous = installedSkills
    setInstalledSkills((prev) => prev.filter((skill) => skill.skill_id !== skillId))
    try {
      const response = await fetch(apiUrl(`/api/skills/${skillId}`), {
        method: 'DELETE',
        credentials: 'include',
      })
      await readJson(response)
    } catch (error) {
      setInstalledSkills(previous)
      throw error
    }
  }, [installedSkills])

  const updatePolicy = useCallback(async (next: Partial<AdminSkillsPolicy>) => {
    const merged = { ...policy, ...next }
    setPolicy(merged)
    try {
      const response = await fetch(apiUrl('/api/admin/skills/policy'), {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(merged),
      })
      const data = await readJson(response)
      setPolicy({ ...DEFAULT_POLICY, ...(data.policy ?? merged) })
    } catch (error) {
      setPolicy(policy)
      throw error
    }
  }, [policy])

  return useMemo(
    () => ({ installedSkills, policy, loading, refresh, toggleSkill, uninstallSkill, updatePolicy }),
    [installedSkills, loading, policy, refresh, toggleSkill, uninstallSkill, updatePolicy],
  )
}
