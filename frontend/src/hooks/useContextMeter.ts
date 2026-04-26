import { useCallback, useRef, useState } from 'react'
import { contextLengthForModel } from '../lib/models'
import type {
  RuntimeCompactionCheckpoint,
  RuntimeContextMeter,
  RuntimeMeterBucket,
} from './useWebSocket'

// Source-of-truth for the context meter values: ``'heuristic'`` is the
// legacy ``addTokens`` estimator from chat log entries; ``'runtime'``
// means the agent_loop dispatch hook has emitted at least one
// ``context_meter`` runtime event for this session.
export type ContextMeterSource = 'heuristic' | 'runtime'

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
  /**
   * Phase 9 source-of-truth flag. Once ``'runtime'`` we trust the
   * agent_loop dispatch hook over the heuristic ``addTokens`` math.
   */
  source: ContextMeterSource
  /**
   * Eight-bucket breakdown from the most recent runtime
   * ``context_meter`` event when ``source === 'runtime'``. Matches
   * :func:`backend.runtime.context_window._build_meter`.
   */
  buckets: RuntimeMeterBucket[]
  /** Latest projected percentage reported by the backend (0–100). */
  projectedPct: number
  /**
   * Backend-side compaction threshold (0–100). When the dispatch hook
   * sees ``projected_pct >= compactThresholdPct`` it persists a
   * checkpoint and rewrites the next prompt.
   */
  compactThresholdPct: number
}

const COMPACTION_THRESHOLD = 0.85 // trigger at 85% (heuristic fallback only)
const COMPACTION_TARGET = 0.40    // compact down to ~40% (heuristic fallback only)
const DEFAULT_COMPACT_THRESHOLD_PCT = 90 // mirrors backend default until first runtime event

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

function buildState(
  snap: TaskContextSnapshot,
  source: ContextMeterSource,
  buckets: RuntimeMeterBucket[],
  projectedPct: number,
  compactThresholdPct: number,
): ContextMeterState {
  const pct = snap.contextLimit > 0 ? Math.min(100, (snap.tokensUsed / snap.contextLimit) * 100) : 0
  // When we have a backend-reported projected_pct prefer it: the
  // backend rounds to one decimal and includes overhead the heuristic
  // can't see (system prompt, active_tools, checkpoints, …).
  const effectivePercent = source === 'runtime' && Number.isFinite(projectedPct)
    ? Math.min(100, Math.max(0, projectedPct))
    : pct
  return {
    current: snap,
    percent: effectivePercent,
    isCompacting: snap.compacting,
    source,
    buckets,
    projectedPct: Number.isFinite(projectedPct) ? projectedPct : effectivePercent,
    compactThresholdPct,
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
  /**
   * Once the agent_loop dispatch hook has emitted a real
   * ``context_meter`` event we stop trusting the heuristic
   * ``addTokens`` math — every subsequent dispatch (including
   * background heartbeats) re-emits the truthful meter, and the
   * heuristic would only drift the bar away from reality. The flag is
   * sticky for the lifetime of the hook.
   */
  const sourceRef = useRef<ContextMeterSource>('heuristic')
  const bucketsRef = useRef<RuntimeMeterBucket[]>([])
  const projectedPctRef = useRef<number>(0)
  const compactThresholdPctRef = useRef<number>(DEFAULT_COMPACT_THRESHOLD_PCT)
  // Last truthful runtime tokensUsed / contextLimit, retained so that
  // when the user switches tasks while the runtime meter is the
  // source-of-truth we can hydrate the new task's snapshot with the
  // shared session footprint instead of falling back to 0/limit. The
  // backend keeps a single context window per session across channels,
  // so the displayed footprint must follow it across task switches.
  const runtimeTokensUsedRef = useRef<number>(0)
  const runtimeContextLimitRef = useRef<number>(0)

  const [state, setState] = useState<ContextMeterState>(() =>
    buildState(emptySnapshot(currentModelId), 'heuristic', [], 0, DEFAULT_COMPACT_THRESHOLD_PCT),
  )

  /** Derive percentage using current refs for source / buckets / projected_pct. */
  const withPercent = useCallback(
    (snap: TaskContextSnapshot): ContextMeterState =>
      buildState(
        snap,
        sourceRef.current,
        bucketsRef.current,
        projectedPctRef.current,
        compactThresholdPctRef.current,
      ),
    [],
  )

  // ── Switch active task ─────────────────────────────────────────

  const switchTask = useCallback(
    (taskId: string) => {
      activeTaskRef.current = taskId
      const existing = snapshots.current.get(taskId)
      // When the runtime meter is the source-of-truth, the displayed
      // footprint is session-wide (the backend reports one prepared
      // context window per session id, regardless of which task /
      // channel triggered the dispatch). Override the per-task
      // ``tokensUsed`` / ``contextLimit`` with the latest runtime
      // values so the bar doesn't drop to 0 every time the user
      // switches threads in the sidebar.
      const runtimeOverride = sourceRef.current === 'runtime'
        && runtimeContextLimitRef.current > 0
      if (existing) {
        const updated: TaskContextSnapshot = runtimeOverride
          ? {
              ...existing,
              modelId: currentModelId,
              tokensUsed: runtimeTokensUsedRef.current,
              contextLimit: runtimeContextLimitRef.current,
            }
          : {
              ...existing,
              modelId: currentModelId,
              contextLimit: contextLengthForModel(currentModelId),
            }
        snapshots.current.set(taskId, updated)
        setState(withPercent(updated))
      } else {
        const fresh: TaskContextSnapshot = runtimeOverride
          ? {
              ...emptySnapshot(currentModelId),
              tokensUsed: runtimeTokensUsedRef.current,
              contextLimit: runtimeContextLimitRef.current,
            }
          : emptySnapshot(currentModelId)
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
      // Once the backend has reported a truthful meter we stop
      // double-accounting via the heuristic. Returning ``shouldCompact:
      // false`` keeps the legacy auto-compaction simulator from firing
      // — the runtime owns compaction decisions now.
      if (sourceRef.current === 'runtime') {
        return { shouldCompact: false }
      }
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

  // ── Phase 9: truthful runtime meter ingest ──────────────────────

  /**
   * Replace the active task's snapshot with the truthful, eight-bucket
   * meter the agent_loop dispatch hook emits before every model run.
   * This supersedes the heuristic ``addTokens`` math; once any meter
   * has been applied the heuristic path stops mutating state.
   *
   * The meter's ``model_context_window`` is the size the backend
   * actually uses for compaction decisions, which can differ from
   * ``contextLengthForModel(modelId)`` (e.g. when the operator caps
   * ``RUNTIME_CONTEXT_WINDOW_TOKENS``) — we mirror the backend value
   * so the bar percentage matches reality.
   */
  const applyRuntimeMeter = useCallback(
    (meter: RuntimeContextMeter) => {
      sourceRef.current = 'runtime'
      bucketsRef.current = Array.isArray(meter.buckets) ? meter.buckets : []
      projectedPctRef.current = typeof meter.projected_pct === 'number' ? meter.projected_pct : 0
      compactThresholdPctRef.current =
        typeof meter.compact_threshold_pct === 'number'
          ? meter.compact_threshold_pct
          : DEFAULT_COMPACT_THRESHOLD_PCT
      const taskId = activeTaskRef.current
      const snap = snapshots.current.get(taskId) ?? emptySnapshot(currentModelId)
      const window = typeof meter.model_context_window === 'number' && meter.model_context_window > 0
        ? meter.model_context_window
        : snap.contextLimit
      const tokensUsed = typeof meter.total_tokens === 'number' ? meter.total_tokens : snap.tokensUsed
      // Cache the latest truthful values so ``switchTask`` can apply
      // them to whatever task the user navigates to next without
      // waiting for another dispatch.
      runtimeTokensUsedRef.current = tokensUsed
      runtimeContextLimitRef.current = window
      const updated: TaskContextSnapshot = {
        ...snap,
        tokensUsed,
        contextLimit: window,
      }
      snapshots.current.set(taskId, updated)
      setState(withPercent(updated))
    },
    [currentModelId, withPercent],
  )

  /**
   * Mark the active task as compacted in response to a
   * ``compaction_checkpoint`` runtime event. The next ``context_meter``
   * event will report the post-compaction footprint, so we do not
   * touch ``tokensUsed`` here — only the lifecycle flags.
   */
  const applyCompactionCheckpoint = useCallback(
    (_checkpoint: RuntimeCompactionCheckpoint) => {
      sourceRef.current = 'runtime'
      const taskId = activeTaskRef.current
      const snap = snapshots.current.get(taskId) ?? emptySnapshot(currentModelId)
      const updated: TaskContextSnapshot = {
        ...snap,
        compacted: true,
        compacting: false,
        compactionCount: snap.compactionCount + 1,
      }
      snapshots.current.set(taskId, updated)
      setState(withPercent(updated))
    },
    [currentModelId, withPercent],
  )

  // ── Reset (new session) ────────────────────────────────────────

  const reset = useCallback(() => {
    snapshots.current.clear()
    activeTaskRef.current = 'idle'
    sourceRef.current = 'heuristic'
    bucketsRef.current = []
    projectedPctRef.current = 0
    compactThresholdPctRef.current = DEFAULT_COMPACT_THRESHOLD_PCT
    runtimeTokensUsedRef.current = 0
    runtimeContextLimitRef.current = 0
    setState(buildState(emptySnapshot(currentModelId), 'heuristic', [], 0, DEFAULT_COMPACT_THRESHOLD_PCT))
  }, [currentModelId])

  return {
    ...state,
    switchTask,
    updateModel,
    addTokens,
    setTokens,
    startCompacting,
    finishCompacting,
    applyRuntimeMeter,
    applyCompactionCheckpoint,
    reset,
  }
}
