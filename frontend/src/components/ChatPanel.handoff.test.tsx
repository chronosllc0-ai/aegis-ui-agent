import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { HandoffRequestCard } from './ChatPanel'

describe('HandoffRequestCard', () => {
  it('renders reason/instructions and emits continue request id', () => {
    const onContinue = vi.fn()
    render(
      <HandoffRequestCard
        reason='CAPTCHA detected'
        instructions='Solve CAPTCHA then continue'
        continueLabel='Continue now'
        requestId='handoff-1'
        onContinue={onContinue}
      />,
    )

    expect(screen.getByText('CAPTCHA detected')).toBeInTheDocument()
    expect(screen.getByText('Solve CAPTCHA then continue')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Continue now' }))
    expect(onContinue).toHaveBeenCalledWith('handoff-1')
  })
})
