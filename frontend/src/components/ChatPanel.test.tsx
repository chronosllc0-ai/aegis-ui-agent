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

describe('ChatPanel noise filtering + thinking row spacing', () => {
  it('hard-deny filters noisy status artifacts from logs and server messages', async () => {
    const noisyLogs: LogEntry[] = [
      {
        id: 'noise-log-1',
        taskId: 'task-noise',
        type: 'step',
        status: 'in_progress',
        timestamp: '10:00 AM',
        stepKind: 'other',
        message: '(no tool call): intermediary trace',
        elapsedSeconds: 1,
      },
      {
        id: 'noise-log-2',
        taskId: 'task-noise',
        type: 'step',
        status: 'in_progress',
        timestamp: '10:00 AM',
        stepKind: 'other',
        message: 'Session settings updated',
        elapsedSeconds: 1,
      },
      {
        id: 'noise-log-3',
        taskId: 'task-noise',
        type: 'step',
        status: 'in_progress',
        timestamp: '10:00 AM',
        stepKind: 'other',
        message: 'Workflow step update',
        elapsedSeconds: 1,
      },
      {
        id: 'clean-log-1',
        taskId: 'task-noise',
        type: 'step',
        status: 'completed',
        timestamp: '10:00 AM',
        stepKind: 'other',
        message: 'Model response: Visible assistant text',
        elapsedSeconds: 2,
      },
      {
        id: 'browser-log-1',
        taskId: 'task-noise',
        type: 'step',
        status: 'completed',
        timestamp: '10:00 AM',
        stepKind: 'other',
        message: '[extract_page] Reading page structure',
        elapsedSeconds: 2,
      },
      {
        id: 'browser-log-2',
        taskId: 'task-noise',
        type: 'step',
        status: 'completed',
        timestamp: '10:00 AM',
        stepKind: 'other',
        message: '[go_back] Going back',
        elapsedSeconds: 2,
      },
      {
        id: 'browser-log-3',
        taskId: 'task-noise',
        type: 'step',
        status: 'completed',
        timestamp: '10:00 AM',
        stepKind: 'other',
        message: '[click] Clicking button',
        elapsedSeconds: 2,
      },
      {
        id: 'browser-log-4',
        taskId: 'task-noise',
        type: 'step',
        status: 'completed',
        timestamp: '10:00 AM',
        stepKind: 'other',
        message: '[go_to_url] Opening https://example.com',
        elapsedSeconds: 2,
      },
    ]

    render(
      <ChatPanel
        logs={noisyLogs}
        isWorking={false}
        onSend={vi.fn()}
        onUserInputResponse={vi.fn()}
        onDecomposePlan={vi.fn()}
        connectionStatus='connected'
        transcripts={[]}
        onSwitchToBrowser={vi.fn()}
        latestFrame={null}
        activeTaskId='task-noise'
        serverMessages={[
          { id: 'srv-noise-1', role: 'assistant', content: 'Model response (no tool call): hidden' },
          { id: 'srv-noise-2', role: 'assistant', content: 'Workflow step update' },
          { id: 'srv-browser-1', role: 'assistant', content: '[extract_page] historical fixture' },
          { id: 'srv-browser-2', role: 'assistant', content: '[go_back] historical fixture' },
          { id: 'srv-browser-3', role: 'assistant', content: '[click] historical fixture' },
          { id: 'srv-browser-4', role: 'assistant', content: '[go_to_url] historical fixture' },
          { id: 'srv-clean-1', role: 'assistant', content: 'Visible from server' },
        ]}
        {...baseChatPanelProps}
      />,
    )

    await screen.findByText('Visible from server')
    await screen.findByText('Visible assistant text')
    expect(screen.queryByText(/\(no tool call\):/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/model response \(no tool call\):/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/session settings updated/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/workflow step update/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/\[extract_page\]/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/\[go_back\]/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/\[click\]/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/\[go_to_url\]/i)).not.toBeInTheDocument()
  })

  it('matches visual regression snapshot for thinking row alignment classes', async () => {
    const logs: LogEntry[] = [
      {
        id: 'thinking-log-snapshot',
        taskId: 'task-snapshot',
        type: 'reasoning_start',
        status: 'in_progress',
        timestamp: '10:00 AM',
        stepKind: 'other',
        stepId: 'step-align',
        message: '[thinking]',
        elapsedSeconds: 1,
      },
      {
        id: 'assistant-log-snapshot',
        taskId: 'task-snapshot',
        type: 'step',
        status: 'completed',
        timestamp: '10:00 AM',
        stepKind: 'other',
        message: 'Model response: baseline message',
        elapsedSeconds: 1,
      },
    ]

    const { findByTestId } = render(
      <ChatPanel
        logs={logs}
        isWorking={false}
        onSend={vi.fn()}
        onUserInputResponse={vi.fn()}
        onDecomposePlan={vi.fn()}
        connectionStatus='connected'
        transcripts={[]}
        onSwitchToBrowser={vi.fn()}
        latestFrame={null}
        activeTaskId='task-snapshot'
        reasoningMap={{ 'step-align': 'Alignment regression guard text' }}
        serverMessages={[]}
        {...baseChatPanelProps}
      />,
    )

    await screen.findByText('baseline message')
    expect(await findByTestId('thinking-row')).toMatchSnapshot()
    expect(await findByTestId('thinking-row-trigger')).toMatchSnapshot()
  })
})
