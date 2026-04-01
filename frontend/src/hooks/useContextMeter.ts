import { useCallback, useRef, useState } from 'react'
import { contextLengthForModel } from '../lib/models'

// ── Types ──────────────────────────────────────────────────────────

export type TaskContextSnapshot = {
  tokensUsed: number
  modelId: string
  contextLimit: number
  compacted: boolean        // has been compacted at least once
  compacting: boolean       // currently compacting
  compactionCount: number
}

export type ContextMeterState = {
  /** Active task's context usage */
  current: TaskContextSnapshot
  /** Percentage of context consumed (0-100) */
  percent: number
  /** Whether auto-compaction is happening right now */
  isCompacting: boolean
}

const COMPACTION_THRESHOLD = 0.85 // trigger at 85%
const COMPACTION_TARGET = 0.40    // compact down to ~40%

function emptySnapshot(modelId: string): TaskContextSnapshot {
  return {
    tokensUsed: 0,
    modelId,
    contextLimit: contextLengthForModel(modelId),
    compacted: false,
    compacting: false,
    compactionCount: 0,
  }
}

// ── Hook ───────────────────────────────────────────────────────────

export function useContextMeter(currentModelId: string) {
  /**
   * Per-task context snapshots keyed by taskId.
   * When the user switches tasks the meter shows the stored snapshot.
   * New tasks start at 0.
   */
  const snapshots = useRef<Map<string, TaskContextSnapshot>>(new Map())
  const activeTaskRef = useRef<string>('idle')

  const [state, setState] = useState<ContextMeterState>(() => {
    const snap = emptySnapshot(currentModelId)
    return { current: snap, percent: 0, isCompacting: false }
  })

  /** Derive percentage */
  const withPercent = useCallback((snap: TaskContextSnapshot): ContextMeterState => {
    const pct = snap.contextLimit > 0 ? Math.min(100, (snap.tokensUsed / snap.contextLimit) * 100) : 0
    return { current: snap, percent: pct, isCompacting: snap.compacting }
  }, [])

  // ── Switch active task ─────────────────────────────────────────

  const switchTask = useCallback(
    (taskId: string) => {
      activeTaskRef.current = taskId
      const existing = snapshots.current.get(taskId)
      if (existing) {
        // Restore snapshot - update contextLimit if model changed
        const updated = {
          ...existing,
          modelId: currentModelId,
          contextLimit: contextLengthForModel(currentModelId),
        }
        snapshots.current.set(taskId, updated)
        setState(withPercent(updated))
      } else {
        const fresh = emptySnapshot(currentModelId)
        snapshots.current.set(taskId, fresh)
        setState(withPercent(fresh))
      }
    },
    [currentModelId, withPercent],
  )

  // ── Model changed mid-conversation ─────────────────────────────

  const updateModel = useCallback(
    (modelId: string) => {
      const taskId = activeTaskRef.current
      const snap = snapshots.current.get(taskId) ?? emptySnapshot(modelId)
      const updated: TaskContextSnapshot = {
        ...snap,
        modelId,
        contextLimit: contextLengthForModel(modelId),
      }
      snapshots.current.set(taskId, updated)
      setState(withPercent(updated))
    },
    [withPercent],
  )

  // ── Ingest tokens (called on each WS message) ─────────────────

  const addTokens = useCallback(
    (tokens: number): { shouldCompact: boolean } => {
      const taskId = activeTaskRef.current
      const snap = snapshots.current.get(taskId) ?? emptySnapshot(currentModelId)
      const updated: TaskContextSnapshot = { ...snap, tokensUsed: snap.tokensUsed + tokens }
      snapshots.current.set(taskId, updated)
      setState(withPercent(updated))

      const ratio = updated.contextLimit > 0 ? updated.tokensUsed / updated.contextLimit : 0
      return { shouldCompact: ratio >= COMPACTION_THRESHOLD && !updated.compacting }
    },
    [currentModelId, withPercent],
  )

  // ── Set exact token count from backend ─────────────────────────

  const setTokens = useCallback(
    (tokens: number) => {
      const taskId = activeTaskRef.current
      const snap = snapshots.current.get(taskId) ?? emptySnapshot(currentModelId)
      const updated: TaskContextSnapshot = { ...snap, tokensUsed: tokens }
      snapshots.current.set(taskId, updated)
      setState(withPercent(updated))
    },
    [currentModelId, withPercent],
  )

  // ── Compaction lifecycle ───────────────────────────────────────

  const startCompacting = useCallback(() => {
    const taskId = activeTaskRef.current
    const snap = snapshots.current.get(taskId) ?? emptySnapshot(currentModelId)
    const updated: TaskContextSnapshot = { ...snap, compacting: true }
    snapshots.current.set(taskId, updated)
    setState(withPercent(updated))
  }, [currentModelId, withPercent])

  const finishCompacting = useCallback(() => {
    const taskId = activeTaskRef.current
    const snap = snapshots.current.get(taskId) ?? emptySnapshot(currentModelId)
    const compactedTokens = Math.floor(snap.contextLimit * COMPACTION_TARGET)
    const updated: TaskContextSnapshot = {
      ...snap,
      tokensUsed: Math.min(snap.tokensUsed, compactedTokens),
      compacting: false,
      compacted: true,
      compactionCount: snap.compactionCount + 1,
    }
    snapshots.current.set(taskId, updated)
    setState(withPercent(updated))
  }, [currentModelId, withPercent])

  // ── Reset (new session) ────────────────────────────────────────

  const reset = useCallback(() => {
    snapshots.current.clear()
    activeTaskRef.current = 'idle'
    setState(withPercent(emptySnapshot(currentModelId)))
  }, [currentModelId, withPercent])

  return {
    ...state,
    switchTask,
    updateModel,
    addTokens,
    setTokens,
    startCompacting,
    finishCompacting,
    reset,
  }
}
