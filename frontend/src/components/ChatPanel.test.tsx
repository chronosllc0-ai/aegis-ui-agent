import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ChatPanel, resolveComposerSubmission } from './ChatPanel'
import type { LogEntry } from '../hooks/useWebSocket'

const baseChatPanelProps = {
  provider: 'google',
  model: 'gemini-2.5-pro',
  agentMode: 'orchestrator' as const,
  onProviderChange: vi.fn(),
  onModelChange: vi.fn(),
  onAgentModeChange: vi.fn(),
}

afterEach(() => {
  cleanup()
})

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
  it('creates one local user bubble and invokes user_input_response callback exactly once', async () => {
    const onUserInputResponse = vi.fn()
    const onSend = vi.fn()

    render(
      <ChatPanel
        logs={[makeAskUserInputLog()]}
        isWorking={false}
        onSend={onSend}
        onDecomposePlan={vi.fn()}
        connectionStatus='connected'
        transcripts={[]}
        onSwitchToBrowser={vi.fn()}
        latestFrame={null}
        serverMessages={[]}
        activeTaskId='task-1'
        onUserInputResponse={onUserInputResponse}
        {...baseChatPanelProps}
      />,
    )

    await screen.findByText('Choose a path')
    fireEvent.click(screen.getByRole('button', { name: /type your own answer/i }))
    const customInput = screen.getByPlaceholderText('Type your answer...')
    fireEvent.change(customInput, { target: { value: 'Custom answer from user' } })
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))

    expect(onUserInputResponse).toHaveBeenCalledTimes(1)
    expect(onUserInputResponse).toHaveBeenCalledWith('Custom answer from user', 'req-123')
    expect(onSend).not.toHaveBeenCalled()

    const userBubbleTexts = screen
      .getAllByTestId('user-bubble')
      .map((node) => node.textContent ?? '')
      .filter((text) => text.includes('Custom answer from user'))
    expect(userBubbleTexts).toHaveLength(1)

    const persisted = JSON.parse(localStorage.getItem('aegis.chat.task-1') ?? '[]') as Array<{ metadata?: Record<string, unknown> }>
    const localAskReply = persisted.find((msg) => (msg.metadata?.request_id as string | undefined) === 'req-123')
    expect(localAskReply?.metadata?.source).toBe('ask_user_input')
  })
})

describe('resolveComposerSubmission', () => {
  it('parses slash plan command as plan mode', () => {
    expect(resolveComposerSubmission('/plan foo', false)).toEqual({ mode: 'plan', text: 'foo' })
  })

  it('uses plan intent when enabled', () => {
    expect(resolveComposerSubmission('foo', true)).toEqual({ mode: 'plan', text: 'foo' })
  })

  it('keeps normal mode when no slash command or intent', () => {
    expect(resolveComposerSubmission('foo', false)).toEqual({ mode: 'normal', text: 'foo' })
  })
})

describe('ChatPanel plan intent UX', () => {
  it('strips /plan token from visible bubble and routes to plan decompose', async () => {
    const onDecomposePlan = vi.fn()
    const onSend = vi.fn()

    render(
      <ChatPanel
        logs={[]}
        isWorking={false}
        onSend={onSend}
        onUserInputResponse={vi.fn()}
        onDecomposePlan={onDecomposePlan}
        connectionStatus='connected'
        transcripts={[]}
        onSwitchToBrowser={vi.fn()}
        latestFrame={null}
        serverMessages={[]}
        {...baseChatPanelProps}
      />,
    )

    const composers = screen.getAllByPlaceholderText('Ask for a task, research, or code…')
    const composer = composers[composers.length - 1]
    fireEvent.change(composer, { target: { value: '/plan Build onboarding flow' } })
    const sendButtons = screen.getAllByRole('button', { name: 'Send message' })
    fireEvent.click(sendButtons[sendButtons.length - 1])

    expect(onDecomposePlan).toHaveBeenCalledWith('Build onboarding flow')
    expect(onSend).not.toHaveBeenCalled()
    await waitFor(() => {
      expect(screen.getByText('Build onboarding flow')).toBeInTheDocument()
    })
    expect(screen.queryByText('/plan Build onboarding flow')).not.toBeInTheDocument()
  })
})
