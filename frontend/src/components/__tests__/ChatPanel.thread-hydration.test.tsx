import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ChatPanel } from '../ChatPanel'
import type { ServerMessage } from '../../hooks/useConversations'
import type { LogEntry } from '../../hooks/useWebSocket'

function makeServerMessages(thread: 'A' | 'B'): ServerMessage[] {
  return [
    {
      id: `${thread}-user-1`,
      role: 'user',
      content: `Thread ${thread} user`,
      metadata: null,
      created_at: '2026-04-03T10:00:00.000Z',
    },
    {
      id: `${thread}-assistant-1`,
      role: 'assistant',
      content: `Thread ${thread} assistant`,
      metadata: null,
      created_at: '2026-04-03T10:00:05.000Z',
    },
    {
      id: `${thread}-assistant-browser-1`,
      role: 'assistant',
      content: '[extract_page] historical fixture',
      metadata: null,
      created_at: '2026-04-03T10:00:06.000Z',
    },
    {
      id: `${thread}-assistant-browser-2`,
      role: 'assistant',
      content: '[go_back] historical fixture',
      metadata: null,
      created_at: '2026-04-03T10:00:07.000Z',
    },
    {
      id: `${thread}-assistant-browser-3`,
      role: 'assistant',
      content: '[click] historical fixture',
      metadata: null,
      created_at: '2026-04-03T10:00:08.000Z',
    },
    {
      id: `${thread}-assistant-browser-4`,
      role: 'assistant',
      content: '[go_to_url] historical fixture',
      metadata: null,
      created_at: '2026-04-03T10:00:09.000Z',
    },
  ]
}

function makeLogs(thread: 'A' | 'B'): LogEntry[] {
  return [
    {
      id: `${thread}-thinking`,
      taskId: `task-${thread}`,
      type: 'reasoning_start',
      status: 'in_progress',
      timestamp: '10:00 AM',
      stepKind: 'other',
      message: '[thinking]',
      elapsedSeconds: 1,
      stepId: `${thread}-step-1`,
    },
    {
      id: `${thread}-tool`,
      taskId: `task-${thread}`,
      type: 'step',
      status: 'completed',
      timestamp: '10:00 AM',
      stepKind: 'other',
      message: `[run_code] echo thread-${thread}`,
      elapsedSeconds: 1,
    },
    {
      id: `${thread}-ask`,
      taskId: `task-${thread}`,
      type: 'step',
      status: 'in_progress',
      timestamp: '10:01 AM',
      stepKind: 'other',
      message: `[ask_user_input] {"question":"Choose ${thread}","options":["Option ${thread}"],"request_id":"req-${thread}"}`,
      elapsedSeconds: 1,
    },
  ]
}

describe('ChatPanel thread hydration and per-thread UI restore', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('rehydrates on A/B/A same-length thread switching without stale rows', async () => {
    const onUserInputResponse = vi.fn()

    const { rerender } = render(
      <ChatPanel
        logs={makeLogs('A')}
        isWorking={false}
        onSend={vi.fn()}
        onDecomposePlan={vi.fn()}
        connectionStatus='connected'
        transcripts={[]}
        onSwitchToBrowser={vi.fn()}
        latestFrame={null}
        activeTaskId='task-A'
        serverMessages={makeServerMessages('A')}
        onUserInputResponse={onUserInputResponse}
      />,
    )

    await screen.findByText('Thread A assistant')
    expect(screen.queryByText(/\[extract_page\]/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/\[go_back\]/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/\[click\]/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/\[go_to_url\]/i)).not.toBeInTheDocument()

    expect(screen.queryByText('Thinking')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '1. Option A' }))
    expect(onUserInputResponse).toHaveBeenCalledWith('Option A', 'req-A')
    expect(screen.getByText('You answered this question.')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Shell — run code/i }))
    expect(screen.getByRole('button', { name: /Ranrun code echo thread-A/i })).toBeInTheDocument()

    rerender(
      <ChatPanel
        logs={makeLogs('B')}
        isWorking={false}
        onSend={vi.fn()}
        onDecomposePlan={vi.fn()}
        connectionStatus='connected'
        transcripts={[]}
        onSwitchToBrowser={vi.fn()}
        latestFrame={null}
        activeTaskId='task-B'
        serverMessages={makeServerMessages('B')}
        onUserInputResponse={onUserInputResponse}
      />,
    )

    await screen.findByText('Thread B assistant')
    expect(screen.queryByText('Thread A assistant')).not.toBeInTheDocument()
    expect(screen.queryByText(/\[extract_page\]/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/\[go_back\]/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/\[click\]/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/\[go_to_url\]/i)).not.toBeInTheDocument()

    rerender(
      <ChatPanel
        logs={makeLogs('A')}
        isWorking={false}
        onSend={vi.fn()}
        onDecomposePlan={vi.fn()}
        connectionStatus='connected'
        transcripts={[]}
        onSwitchToBrowser={vi.fn()}
        latestFrame={null}
        activeTaskId='task-A'
        serverMessages={makeServerMessages('A')}
        onUserInputResponse={onUserInputResponse}
      />,
    )

    await screen.findByText('Thread A assistant')

    expect(screen.getByText('You answered this question.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Ranrun code echo thread-A/i })).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.queryByText('Thread B assistant')).not.toBeInTheDocument()
      expect(screen.queryByText('Thinking')).not.toBeInTheDocument()
    })

    expect(screen.getAllByText('Thread A user')).toHaveLength(1)

    const renderSignature = {
      userBubbles: screen
        .getAllByTestId('user-bubble')
        .map((node) => (node.textContent ?? '').replace(/\d{1,2}:\d{2}(?::\d{2})?\s[AP]M/g, 'TIME'))
        .sort(),
      answered: !!screen.queryByText('You answered this question.'),
      toolCollapsed: !!screen.queryByRole('button', { name: /Ranrun code echo thread-A/i }),
      reasoningOpen: !!screen.queryByText('Thinking'),
    }
    expect(renderSignature).toMatchInlineSnapshot(`
      {
        "answered": true,
        "reasoningOpen": false,
        "toolCollapsed": true,
        "userBubbles": [
          "Option ATIME",
          "Thread A userTIME",
        ],
      }
    `)
  })
})
