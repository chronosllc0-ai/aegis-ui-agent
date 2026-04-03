import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ChatPanel } from './ChatPanel'
import type { LogEntry } from '../hooks/useWebSocket'

function makeAskUserInputLog(): LogEntry {
  return {
    id: 'log-ask-1',
    taskId: 'task-1',
    type: 'step',
    status: 'in_progress',
    timestamp: '10:00 AM',
    stepKind: 'other',
    message: '[ask_user_input] {"question":"Choose a path","options":["Option A"],"request_id":"req-123"}',
    elapsedSeconds: 1,
  }
}

describe('ChatPanel ask_user_input reply flow', () => {
  it('creates one local user bubble and invokes user_input_response callback exactly once', () => {
    const onUserInputResponse = vi.fn()

    render(
      <ChatPanel
        logs={[makeAskUserInputLog()]}
        isWorking={false}
        onSend={vi.fn()}
        onDecomposePlan={vi.fn()}
        connectionStatus='connected'
        transcripts={[]}
        onSwitchToBrowser={vi.fn()}
        latestFrame={null}
        serverMessages={[]}
        onUserInputResponse={onUserInputResponse}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /type your own answer/i }))
    const customInput = screen.getByPlaceholderText('Type your answer...')
    fireEvent.change(customInput, { target: { value: 'Custom answer from user' } })
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))

    expect(onUserInputResponse).toHaveBeenCalledTimes(1)
    expect(onUserInputResponse).toHaveBeenCalledWith('Custom answer from user', 'req-123')

    const userBubbleTexts = screen
      .getAllByTestId('user-bubble')
      .map((node) => node.textContent ?? '')
      .filter((text) => text.includes('Custom answer from user'))
    expect(userBubbleTexts).toHaveLength(1)
  })
})
