import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ChatPanel, resolveComposerSubmission } from './ChatPanel'
import type { LogEntry } from '../hooks/useWebSocket'

const baseChatPanelProps = {
  provider: 'google',
  model: 'gemini-2.5-pro',
  agentMode: 'orchestrator' as const,
  mode: 'steer' as const,
  queuedMessages: [],
  onModeChange: vi.fn(),
  onPrimarySend: vi.fn(),
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
    const onPrimarySend = vi.fn()
    const onSend = vi.fn()

    render(
      <ChatPanel
        logs={[makeAskUserInputLog()]}
        isWorking={false}
        onPrimarySend={onPrimarySend}
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
    expect(onPrimarySend).not.toHaveBeenCalled()

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
    const onPrimarySend = vi.fn()
    const onSend = vi.fn()

    render(
      <ChatPanel
        logs={[]}
        isWorking={false}
        onPrimarySend={onPrimarySend}
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
    expect(onPrimarySend).not.toHaveBeenCalled()
    await waitFor(() => {
      expect(screen.getByText('Build onboarding flow')).toBeInTheDocument()
    })
    expect(screen.queryByText('/plan Build onboarding flow')).not.toBeInTheDocument()
  })
})

describe('ChatPanel steering control in composer', () => {
  it('shows task stop control only while a task is running', () => {
    const { rerender } = render(
      <ChatPanel
        logs={[]}
        isWorking={true}
        onSend={vi.fn()}
        onUserInputResponse={vi.fn()}
        onDecomposePlan={vi.fn()}
        connectionStatus='connected'
        transcripts={[]}
        onSwitchToBrowser={vi.fn()}
        latestFrame={null}
        serverMessages={[]}
        {...baseChatPanelProps}
      />,
    )

    expect(screen.getAllByRole('button', { name: 'Stop task' }).length).toBeGreaterThan(0)

    rerender(
      <ChatPanel
        logs={[]}
        isWorking={false}
        onSend={vi.fn()}
        onUserInputResponse={vi.fn()}
        onDecomposePlan={vi.fn()}
        connectionStatus='connected'
        transcripts={[]}
        onSwitchToBrowser={vi.fn()}
        latestFrame={null}
        serverMessages={[]}
        {...baseChatPanelProps}
      />,
    )

    expect(screen.queryByRole('button', { name: 'Stop task' })).not.toBeInTheDocument()
  })

  it('routes outbound send action while running', () => {
    const onPrimarySend = vi.fn()
    const onSend = vi.fn()

    render(
      <ChatPanel
        {...baseChatPanelProps}
        logs={[]}
        isWorking={false}
        onPrimarySend={onPrimarySend}
        onSend={onSend}
        onUserInputResponse={vi.fn()}
        onDecomposePlan={vi.fn()}
        connectionStatus='connected'
        transcripts={[]}
        onSwitchToBrowser={vi.fn()}
        latestFrame={null}
        serverMessages={[]}
      />,
    )

    const composers = screen.getAllByPlaceholderText('Ask for a task, research, or code…')
    const composer = composers[composers.length - 1]
    fireEvent.change(composer, { target: { value: 'Do the next thing' } })
    fireEvent.keyDown(composer, { key: 'Enter', code: 'Enter' })

    expect(onPrimarySend).toHaveBeenCalledWith(
      'Do the next thing',
      expect.objectContaining({ task_label: 'Do the next thing' }),
    )
    expect(onSend).not.toHaveBeenCalled()
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
    await screen.findByText('Model response: Visible assistant text')
    expect(screen.queryByText(/\(no tool call\):/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/model response \(no tool call\):/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/session settings updated/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/workflow step update/i)).not.toBeInTheDocument()
    expect(screen.getByText(/shell — extract page/i)).toBeInTheDocument()
    expect(screen.getByText(/shell — go back/i)).toBeInTheDocument()
    expect(screen.getByText(/shell — click/i)).toBeInTheDocument()
    expect(screen.getByText(/shell — go to url/i)).toBeInTheDocument()
  })

  it('shows one live activity accordion instead of repeated thinking rows', async () => {
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

    render(
      <ChatPanel
        logs={logs}
        isWorking
        onSend={vi.fn()}
        onUserInputResponse={vi.fn()}
        onDecomposePlan={vi.fn()}
        connectionStatus='connected'
        transcripts={[]}
        onSwitchToBrowser={vi.fn()}
        latestFrame={null}
        activeTaskId='task-snapshot'
        isActivityVisible
        activityStatusLabel='Aegis is thinking…'
        activityDetail='Alignment regression guard text'
        serverMessages={[]}
        {...baseChatPanelProps}
      />,
    )

    await screen.findByText('Model response: baseline message')
    expect(screen.getAllByText('Aegis is thinking…')).toHaveLength(1)
    expect(screen.getByText('Reasoning')).toBeInTheDocument()
  })
})

describe('ChatPanel tool call request/response sections', () => {
  it('renders Request and Response dropdowns only for successful typed tool calls', async () => {
    const logs: LogEntry[] = [
      {
        id: 'typed-tool-success',
        taskId: 'task-tools',
        type: 'step',
        status: 'completed',
        timestamp: '10:00 AM',
        stepKind: 'other',
        message: JSON.stringify({
          tool: 'update_resource',
          call_id: 'call-1',
          args: { resourceId: 'abc-123', patch: { enabled: true } },
        }),
        elapsedSeconds: 1,
        rawStepType: 'tool_result',
        toolCallId: 'call-1',
        toolResult: '{"success":true}',
        toolOk: true,
      },
    ]

    render(
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
        serverMessages={[]}
        {...baseChatPanelProps}
      />,
    )

    await screen.findByText(/update resource/i)
    expect(screen.getByRole('button', { name: 'Request' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Response' })).toBeInTheDocument()
  })

  it('keeps failure-state card layout without request/response dropdowns', async () => {
    const logs: LogEntry[] = [
      {
        id: 'typed-tool-failed',
        taskId: 'task-tools',
        type: 'step',
        status: 'completed',
        timestamp: '10:00 AM',
        stepKind: 'other',
        message: JSON.stringify({
          tool: 'update_resource',
          call_id: 'call-2',
          args: { resourceId: 'abc-123' },
        }),
        elapsedSeconds: 1,
        rawStepType: 'tool_result',
        toolCallId: 'call-2',
        toolResult: '{"error":"boom"}',
        toolOk: false,
      },
    ]

    render(
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
        serverMessages={[]}
        {...baseChatPanelProps}
      />,
    )

    await screen.findByText(/update resource/i)
    expect(screen.queryByRole('button', { name: 'Request' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Response' })).not.toBeInTheDocument()
    expect(screen.getByText('failed')).toBeInTheDocument()
  })
})
