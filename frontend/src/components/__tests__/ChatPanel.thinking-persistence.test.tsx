import { render, screen } from '@testing-library/react'
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
    onUserInputResponse: vi.fn(),
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

  it('does not render repeated thinking rows on A/B/A task switch', () => {
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
    expect(screen.queryByText('Thinking')).not.toBeInTheDocument()
    expect(screen.queryByText('[thinking]')).not.toBeInTheDocument()

    rerender(<ChatPanel {...baseProps({ logs: [], activeTaskId: 'task-b' })} />)
    expect(screen.queryByText('Thinking')).not.toBeInTheDocument()

    rerender(<ChatPanel {...baseProps({ logs, activeTaskId: 'task-a' })} />)
    expect(screen.queryByText('Thinking')).not.toBeInTheDocument()
  })

  it('renders exactly one live activity accordion while working', () => {
    saveThinking('task-a', 'step-1', 'streaming')

    render(
      <ChatPanel
        {...baseProps({ activeTaskId: 'task-a', isWorking: true })}
        taskActivity={{ phase: 'thinking', detail: 'live reasoning', updatedAt: '2026-04-03T00:00:00.000Z' }}
      />,
    )
    expect(screen.getAllByText('Aegis is thinking…')).toHaveLength(1)
    expect(screen.queryByText('Thinking')).not.toBeInTheDocument()
  })
})
