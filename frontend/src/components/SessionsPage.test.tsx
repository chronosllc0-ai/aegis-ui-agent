import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { SessionsPage } from './SessionsPage'

describe('SessionsPage', () => {
  it('supports filter + session open action', () => {
    const onOpenSession = vi.fn()
    render(
      <SessionsPage
        sessions={[
          { session_id: 'agent:main:main', parent_session_id: null, title: 'main', status: 'active', created_at: null, updated_at: new Date().toISOString() },
          { session_id: 'agent:main:heartbeat', parent_session_id: 'agent:main:main', title: 'heartbeat', status: 'active', created_at: null, updated_at: new Date().toISOString() },
        ]}
        onRefresh={vi.fn()}
        onOpenSession={onOpenSession}
      />,
    )

    fireEvent.change(screen.getByPlaceholderText(/filter by key/i), { target: { value: 'heartbeat' } })
    fireEvent.click(screen.getByRole('button', { name: 'agent:main:heartbeat' }))
    expect(onOpenSession).toHaveBeenCalledWith('agent:main:heartbeat')
  })
})
