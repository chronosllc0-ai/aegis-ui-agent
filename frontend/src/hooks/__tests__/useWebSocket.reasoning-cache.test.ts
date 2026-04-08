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

  constructor(_url: string) {
    MockWebSocket.instances.push(this)
    window.setTimeout(() => this.onopen?.(new Event('open')), 0)
  }

  send(_data: string): void {}

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
