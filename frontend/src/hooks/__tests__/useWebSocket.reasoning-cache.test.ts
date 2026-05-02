import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useWebSocket } from '../useWebSocket'

class MockWebSocket {
  static instances: MockWebSocket[] = []
  static OPEN = 1
  static CONNECTING = 0
  static CLOSING = 2
  static CLOSED = 3

  readyState = MockWebSocket.OPEN
  onopen: ((event: Event) => void) | null = null
  onclose: ((event: Event) => void) | null = null
  onerror: (() => void) | null = null
  onmessage: ((event: MessageEvent<string>) => void) | null = null
  sent: string[] = []

  constructor(_url: string) {
    MockWebSocket.instances.push(this)
    window.setTimeout(() => this.onopen?.(new Event('open')), 0)
  }

  send(data: string): void {
    this.sent.push(data)
  }

  close(): void {
    this.readyState = MockWebSocket.CLOSED
    this.onclose?.(new Event('close'))
  }

  emit(payload: Record<string, unknown>): void {
    this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent<string>)
  }
}

describe('useWebSocket reasoning cache persistence', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.unstubAllEnvs()
    localStorage.clear()
    MockWebSocket.instances = []
    vi.stubGlobal('WebSocket', MockWebSocket)
  })

  it('persists reasoning_start + deltas and marks streaming rows completed on result', () => {
    const { result } = renderHook(() => useWebSocket())

    act(() => {
      vi.runOnlyPendingTimers()
    })

    const ws = MockWebSocket.instances[0]
    expect(ws).toBeTruthy()

    act(() => {
      result.current.send({ action: 'navigate', instruction: 'Open docs' })
    })

    const taskId = result.current.activeTaskIdRef.current
    const key = `aegis.reasoning.${taskId}`

    act(() => {
      ws.emit({ type: 'reasoning_start', data: { step_id: 'step-1' } })
      ws.emit({ type: 'reasoning_delta', data: { step_id: 'step-1', delta: 'first ' } })
      ws.emit({ type: 'reasoning_delta', data: { step_id: 'step-1', delta: 'second' } })
    })

    const streaming = JSON.parse(localStorage.getItem(key) ?? '[]')
    expect(streaming).toHaveLength(1)
    expect(streaming[0].stepId).toBe('step-1')
    expect(streaming[0].text).toBe('first second')
    expect(streaming[0].status).toBe('streaming')

    act(() => {
      ws.emit({ type: 'result', data: { status: 'completed' } })
    })

    const completed = JSON.parse(localStorage.getItem(key) ?? '[]')
    expect(completed[0].status).toBe('completed')
  })

  it('does not reconnect just because option callback identities change', () => {
    const { rerender } = renderHook(
      ({ version: _version }: { version: number }) => useWebSocket({
        onUsageMessage: vi.fn(),
        onRuntimeSession: vi.fn(),
        onRuntimeContextMeter: vi.fn(),
        onRuntimeCompactionCheckpoint: vi.fn(),
      }),
      { initialProps: { version: 1 } },
    )

    act(() => {
      vi.runOnlyPendingTimers()
    })

    expect(MockWebSocket.instances).toHaveLength(1)

    rerender({ version: 2 })

    act(() => {
      vi.advanceTimersByTime(0)
    })

    expect(MockWebSocket.instances).toHaveLength(1)
  })

  it('does not fail after a task_state queued event because chat no longer has a queued watchdog', () => {
    vi.stubEnv('VITE_NAVIGATE_ACK_TIMEOUT_MS', '5000')
    vi.stubEnv('VITE_BACKEND_ACTIVITY_TIMEOUT_MS', '3000')

    const { result } = renderHook(() => useWebSocket())

    act(() => {
      vi.runOnlyPendingTimers()
    })

    const ws = MockWebSocket.instances[0]
    expect(ws).toBeTruthy()

    act(() => {
      result.current.send({ action: 'navigate', instruction: 'Say hi' })
    })

    const outbound = JSON.parse(ws.sent.at(-1) ?? '{}') as { request_id?: string }
    expect(outbound.request_id).toBeTruthy()

    act(() => {
      ws.emit({ type: 'navigate_ack', data: { request_id: outbound.request_id, task_id: 'server-task', accepted: true } })
      ws.emit({ type: 'task_state', data: { task_id: 'server-task', state: 'queued' } })
      vi.advanceTimersByTime(20_050)
    })

    expect(result.current.executionState).toBe('starting')
    expect(result.current.isWorking).toBe(true)
    expect(result.current.logs.some((entry) => entry.message.includes('Task stayed queued too long'))).toBe(false)
  })

  it('fails a queued task only when no runtime progress arrives before the post-queue timeout', () => {
    vi.stubEnv('VITE_NAVIGATE_ACK_TIMEOUT_MS', '5000')
    vi.stubEnv('VITE_BACKEND_ACTIVITY_TIMEOUT_MS', '3000')
    vi.stubEnv('VITE_NAVIGATE_POST_QUEUE_PROGRESS_TIMEOUT_MS', '100')

    const { result } = renderHook(() => useWebSocket())

    act(() => {
      vi.runOnlyPendingTimers()
    })

    const ws = MockWebSocket.instances[0]
    expect(ws).toBeTruthy()

    act(() => {
      result.current.send({ action: 'navigate', instruction: 'Say hi' })
    })

    const outbound = JSON.parse(ws.sent.at(-1) ?? '{}') as { request_id?: string }
    expect(outbound.request_id).toBeTruthy()

    act(() => {
      ws.emit({ type: 'navigate_ack', data: { request_id: outbound.request_id, task_id: 'server-task', accepted: true } })
      ws.emit({ type: 'task_state', data: { task_id: 'server-task', state: 'queued' } })
      vi.advanceTimersByTime(101)
    })

    expect(result.current.executionState).toBe('failed')
    expect(result.current.isWorking).toBe(false)
    expect(result.current.logs.some((entry) => entry.message.includes('No runtime progress reported after queueing'))).toBe(true)
  })

  it('clears the post-queue timeout when runtime progress arrives', () => {
    vi.stubEnv('VITE_NAVIGATE_ACK_TIMEOUT_MS', '5000')
    vi.stubEnv('VITE_BACKEND_ACTIVITY_TIMEOUT_MS', '3000')
    vi.stubEnv('VITE_NAVIGATE_POST_QUEUE_PROGRESS_TIMEOUT_MS', '100')

    const { result } = renderHook(() => useWebSocket())

    act(() => {
      vi.runOnlyPendingTimers()
    })

    const ws = MockWebSocket.instances[0]
    expect(ws).toBeTruthy()

    act(() => {
      result.current.send({ action: 'navigate', instruction: 'Say hi' })
    })

    const outbound = JSON.parse(ws.sent.at(-1) ?? '{}') as { request_id?: string }
    expect(outbound.request_id).toBeTruthy()

    act(() => {
      ws.emit({ type: 'navigate_ack', data: { request_id: outbound.request_id, task_id: 'server-task', accepted: true } })
      ws.emit({ type: 'task_state', data: { task_id: 'server-task', state: 'queued' } })
      ws.emit({ type: 'runtime_event', channel: 'web', data: { kind: 'run_started', channel: 'web', payload: {} } })
      vi.advanceTimersByTime(101)
    })

    expect(result.current.executionState).toBe('running')
    expect(result.current.isWorking).toBe(true)
    expect(result.current.logs.some((entry) => entry.message.includes('No runtime progress reported after queueing'))).toBe(false)
  })

  it('keeps early reasoning deltas when reasoning_start arrives late', () => {
    const { result } = renderHook(() => useWebSocket())

    act(() => {
      vi.runOnlyPendingTimers()
    })

    const ws = MockWebSocket.instances[0]
    expect(ws).toBeTruthy()

    act(() => {
      result.current.send({ action: 'navigate', instruction: 'Investigate race condition' })
    })

    const taskId = result.current.activeTaskIdRef.current
    const key = `aegis.reasoning.${taskId}`

    act(() => {
      ws.emit({ type: 'reasoning_delta', data: { step_id: 'step-race', delta: 'early ' } })
      ws.emit({ type: 'reasoning_start', data: { step_id: 'step-race' } })
      ws.emit({ type: 'reasoning_delta', data: { step_id: 'step-race', delta: 'late' } })
    })

    const persisted = JSON.parse(localStorage.getItem(key) ?? '[]')
    expect(persisted).toHaveLength(1)
    expect(persisted[0].stepId).toBe('step-race')
    expect(persisted[0].text).toBe('early late')
    expect(result.current.reasoningMap['step-race']).toBe('early late')
  })
})
