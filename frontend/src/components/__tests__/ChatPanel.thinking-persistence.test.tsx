qqimport { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type React from 'react'

import { ChatPanel } from '../ChatPanel'
import type { LogEntry } from '../../hooks/useWebSocket'

function baseProps(overrides: Partial<React.ComponentProps<typeof ChatPanel>> = {}): React.ComponentProps<typeof ChatPanel> {
  return {
    logs: [],
    isWorking: false,
    onSend: vi.fn(),
    onDecomposePlan: vi.fn(),
    connectionStatus: 'connected',
    transcripts: [],
    onSwitchToBrowser: vi.fn(),
    latestFrame: null,
    activeTaskId: 'task-a',
    serverMessages: [],
    reasoningMap: {},
    ...overrides,
  }
}

function saveThinking(taskId: string, stepId = 'step-1', status: 'streaming' | 'completed' = 'streaming'): void {
  localStorage.setItem(
    `aegis.reasoning.${taskId}`,
    JSON.stringify([
      {
        id: `thinking-${taskId}-${stepId}`,
        role: 'thinking',
        taskId,
        stepId,
        status,
        text: status === 'completed' ? 'done reasoning' : 'live reasoning',
        updatedAt: '2026-04-03T00:00:00.000Z',
      },
    ]),
  )
}

describe('ChatPanel thinking persistence', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('restores thinking rows on A/B/A task switch without rendering raw [thinking] token', () => {
    saveThinking('task-a')
    const logs: LogEntry[] = [
      {
        id: 'assistant-1',
        taskId: 'task-a',
        message: 'Model response: done',
        timestamp: '10:00 AM',
        type: 'step',
        status: 'completed',
        stepKind: 'other',
        elapsedSeconds: 1,
      },
    ]

    const { rerender } = render(<ChatPanel {...baseProps({ logs, activeTaskId: 'task-a' })} />)
    expect(screen.getAllByText('Thinking').length).toBeGreaterThan(0)
    expect(screen.queryByText('[thinking]')).not.toBeInTheDocument()

    rerender(<ChatPanel {...baseProps({ logs: [], activeTaskId: 'task-b' })} />)
    expect(screen.queryByText('Thinking')).not.toBeInTheDocument()

    rerender(<ChatPanel {...baseProps({ logs, activeTaskId: 'task-a' })} />)
    expect(screen.getAllByText('Thinking').length).toBeGreaterThan(0)
  })

  it('restores from local cache after refresh and flips from streaming to completed visual state', () => {
    saveThinking('task-a', 'step-1', 'streaming')

    const { unmount } = render(
      <ChatPanel {...baseProps({ activeTaskId: 'task-a', reasoningMap: { 'step-1': 'live reasoning' }, isWorking: true })} />,
    )
    expect(screen.getAllByText('Thinking').length).toBeGreaterThan(0)

    unmount()
    const { rerender } = render(
      <ChatPanel {...baseProps({ activeTaskId: 'task-a', reasoningMap: { 'step-1': 'live reasoning' }, isWorking: true })} />,
    )
    expect(screen.getAllByText('Thinking').length).toBeGreaterThan(0)

    saveThinking('task-a', 'step-1', 'completed')
    rerender(<ChatPanel {...baseProps({ activeTaskId: 'task-a', reasoningMap: { 'step-1': 'done reasoning' }, isWorking: false })} />)
    expect(screen.getByText('Thought')).toBeInTheDocument()
  })

  it('persists thinking accordion open state per task', () => {
    saveThinking('task-a', 'step-open', 'streaming')
    render(<ChatPanel {...baseProps({ activeTaskId: 'task-a', reasoningMap: { 'step-open': 'expanded text' } })} />)

    for (const chip of screen.getAllByText('Thinking')) {
      fireEvent.click(chip)
    }

    const openIds = JSON.parse(localStorage.getItem('aegis.chat.ui.task-a.openThinkingIds') ?? '[]') as string[]
    expect(openIds).toContain('step-open')
    expect(screen.getByText('expanded text')).toBeInTheDocument()
  })
})
