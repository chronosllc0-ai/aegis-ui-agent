import { useCallback, useState } from 'react'
import { apiUrl } from '../lib/api'

type PlanExecutionState = {
  executing: boolean
  error: string | null
}

export function usePlanExecution() {
  const [state, setState] = useState<PlanExecutionState>({ executing: false, error: null })

  const executePlan = useCallback(async (planId: string): Promise<boolean> => {
    setState({ executing: true, error: null })
    try {
      const response = await fetch(apiUrl(`/api/plans/${planId}/execute`), {
        method: 'POST',
        credentials: 'include',
      })
      const data = await response.json()
      if (!data.ok) {
        setState({ executing: false, error: data.detail || 'Execution failed' })
        return false
      }
      setState({ executing: false, error: null })
      return true
    } catch (err) {
      setState({ executing: false, error: err instanceof Error ? err.message : 'Execution failed' })
      return false
    }
  }, [])

  const stopPlan = useCallback(async (planId: string): Promise<boolean> => {
    try {
      const response = await fetch(apiUrl(`/api/plans/${planId}/stop`), {
        method: 'POST',
        credentials: 'include',
      })
      const data = await response.json()
      return Boolean(data.ok)
    } catch {
      return false
    }
  }, [])

  return { ...state, executePlan, stopPlan }
}
