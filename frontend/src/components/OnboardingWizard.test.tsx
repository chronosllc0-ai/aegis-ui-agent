import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'

import { OnboardingWizard } from './OnboardingWizard'
import type { ToastContextValue } from '../hooks/useToast'
import { ToastContext } from '../hooks/useToast'

afterEach(() => cleanup())

function renderWizard() {
  const toastStub: ToastContextValue = {
    toast: vi.fn(),
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  }

  render(
    <ToastContext.Provider value={toastStub}>
      <OnboardingWizard userName='Alex Carter' userEmail='alex@example.com' onComplete={vi.fn()} />
    </ToastContext.Provider>,
  )
}

describe('OnboardingWizard', () => {
  it('renders welcome step and blocks continue until use case is selected', () => {
    renderWizard()

    expect(screen.getByText('What will you use Aegis for?')).toBeInTheDocument()
    const continueButton = screen.getByRole('button', { name: 'Continue' })
    expect(continueButton).toBeDisabled()

    fireEvent.click(screen.getAllByRole('button', { name: /Research/ })[0])
    expect(continueButton).toBeEnabled()
  })

  it('supports step navigation and profile validation', () => {
    renderWizard()

    fireEvent.click(screen.getAllByRole('button', { name: /QA & Testing/ })[0])
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))

    expect(screen.getByRole('heading', { name: 'Your profile' })).toBeInTheDocument()
    const profileContinue = screen.getByRole('button', { name: 'Continue' })
    expect(profileContinue).toBeEnabled()

    const displayNameInput = screen.getByPlaceholderText('Your name')
    fireEvent.change(displayNameInput, { target: { value: '   ' } })
    expect(profileContinue).toBeDisabled()

    fireEvent.change(displayNameInput, { target: { value: 'Aegis User' } })
    expect(profileContinue).toBeEnabled()

    fireEvent.click(screen.getByRole('button', { name: 'Back' }))
    expect(screen.getByText('What will you use Aegis for?')).toBeInTheDocument()
  })

  it('allows provider mode switching and enforces API key validation before connect', () => {
    renderWizard()

    fireEvent.click(screen.getAllByRole('button', { name: /Development/ })[0])
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))

    expect(screen.getByRole('heading', { name: 'Connect your AI model' })).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Paste your google API key')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'OpenAI' }))
    expect(screen.getByPlaceholderText('Paste your openai API key')).toBeInTheDocument()

    const connectButton = screen.getByRole('button', { name: 'Connect key' })
    expect(connectButton).toBeDisabled()

    fireEvent.change(screen.getByPlaceholderText('Paste your openai API key'), { target: { value: '  ' } })
    expect(connectButton).toBeDisabled()

    fireEvent.change(screen.getByPlaceholderText('Paste your openai API key'), { target: { value: 'sk-test' } })
    expect(connectButton).toBeEnabled()
  })
})
