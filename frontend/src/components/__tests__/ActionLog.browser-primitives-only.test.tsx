import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ActionLog } from '../ActionLog'
import { isBrowserPrimitiveActionLogEntry } from '../../lib/actionLogFilter'
import type { LogEntry } from '../../hooks/useWebSocket'

function makeEntry(overrides: Partial<LogEntry>): LogEntry {
  return {
    id: crypto.randomUUID(),
    taskId: 'task-1',
    message: '[click] click login button',
    timestamp: '10:00:00 AM',
    type: 'step',
    status: 'completed',
    stepKind: 'other',
    elapsedSeconds: 1,
    ...overrides,
  }
}

describe('ActionLog browser primitives filtering', () => {
  it('renders only browser primitive tool rows from a mixed stream', () => {
    const mixedEntries: LogEntry[] = [
      makeEntry({ message: '[click] click login button', stepKind: 'click' }),
      makeEntry({ message: '[type_text] type email', stepKind: 'type' }),
      makeEntry({ message: '[scroll] scroll page', stepKind: 'scroll' }),
      makeEntry({ message: '[wait] wait for ui', stepKind: 'other' }),
      makeEntry({ message: '[screenshot] capture viewport', stepKind: 'other' }),
      makeEntry({ message: '[go_to_url] https://example.com', stepKind: 'navigate' }),
      makeEntry({ message: '[go_back] history back', stepKind: 'navigate' }),
      makeEntry({ message: '[exec_shell] rm -rf /tmp/nope', stepKind: 'other' }),
      makeEntry({ message: '[web_search] best widgets', stepKind: 'other' }),
      makeEntry({ message: '[read_file] /tmp/file.txt', stepKind: 'other' }),
      makeEntry({ message: 'Model response: done', stepKind: 'other' }),
      makeEntry({ type: 'reasoning_start', message: 'thinking...', stepKind: 'other' }),
      makeEntry({ type: 'reasoning', message: 'thinking delta...', stepKind: 'other' }),
      makeEntry({ type: 'result', message: 'task complete', stepKind: 'other' }),
      makeEntry({ type: 'error', message: 'tool failed', status: 'failed', stepKind: 'other' }),
      makeEntry({ type: 'interrupt', message: 'interrupted', status: 'steered', stepKind: 'other' }),
      makeEntry({ message: '[request_approval] approve?', stepKind: 'other' }),
      makeEntry({ message: '[ask_user_input] pick one', stepKind: 'other' }),
      makeEntry({ message: '[summarize] summary card', stepKind: 'other' }),
      makeEntry({ message: '[confirm] confirmation card', stepKind: 'other' }),
      makeEntry({
        message: 'Please navigate to example.com and log in',
        stepKind: 'navigate',
        elapsedSeconds: 0,
      }),
    ]

    const actionEntries = mixedEntries.filter(isBrowserPrimitiveActionLogEntry)

    render(
      <ActionLog
        entries={actionEntries}
        showWorkflow={false}
        onToggleWorkflow={() => undefined}
        onSaveWorkflow={() => undefined}
        taskLabels={{}}
      />,
    )

    expect(screen.getByText('[click] click login button')).toBeInTheDocument()
    expect(screen.getByText('[type_text] type email')).toBeInTheDocument()
    expect(screen.getByText('[scroll] scroll page')).toBeInTheDocument()
    expect(screen.getByText('[wait] wait for ui')).toBeInTheDocument()
    expect(screen.getByText('[screenshot] capture viewport')).toBeInTheDocument()
    expect(screen.getByText('[go_to_url] https://example.com')).toBeInTheDocument()
    expect(screen.getByText('[go_back] history back')).toBeInTheDocument()

    expect(screen.queryByText('[exec_shell] rm -rf /tmp/nope')).not.toBeInTheDocument()
    expect(screen.queryByText('[web_search] best widgets')).not.toBeInTheDocument()
    expect(screen.queryByText('[read_file] /tmp/file.txt')).not.toBeInTheDocument()
    expect(screen.queryByText('Model response: done')).not.toBeInTheDocument()
    expect(screen.queryByText('Please navigate to example.com and log in')).not.toBeInTheDocument()

    const taskHeader = screen.getByRole('button', { name: /Task 1/i })
    expect(taskHeader).toBeInTheDocument()
    expect(taskHeader).not.toHaveTextContent('[click] click login button')
  })
})
