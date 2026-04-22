import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { SessionSwitcher } from './SessionSwitcher'

describe('SessionSwitcher', () => {
  it('switches sessions from grouped list', () => {
    const onSelect = vi.fn()
    render(
      <SessionSwitcher
        sessions={[
          { id: 'agent:main:main', label: 'main', channel: 'chat', status: 'active', group: 'main' },
          { id: 'agent:main:telegram:direct:1', label: 'Dr William', channel: 'chat', status: 'idle', group: 'channels' },
        ]}
        selectedSessionId='agent:main:main'
        onSelect={onSelect}
      />,
    )

    fireEvent.click(screen.getAllByRole('button', { name: /main/i })[0])
    fireEvent.click(screen.getByRole('radio', { name: /Dr William/i }))
    expect(onSelect).toHaveBeenCalledWith('agent:main:telegram:direct:1')
  })
})
