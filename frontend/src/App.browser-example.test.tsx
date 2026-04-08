import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const sendSpy = vi.fn()

vi.mock('./hooks/useUsage', () => ({
  useUsage: () => ({
    balance: { balance: 100 },
    handleUsageMessage: vi.fn(),
    resetSession: vi.fn(),
  }),
}))

vi.mock('./hooks/useWebSocket', () => ({
  useWebSocket: () => ({
    connectionStatus: 'connected',
    isWorking: false,
    latestFrame: null,
    logs: [],
    workflowSteps: [],
    currentUrl: 'about:blank',
    transcripts: [],
    send: sendSpy,
    sendAudioChunk: vi.fn(),
    resetClientState: vi.fn(),
    activeTaskIdRef: { current: 'idle' },
    activeConversationId: null,
    reasoningMap: {},
    subAgents: [],
    subAgentSteps: {},
    messageSubAgent: vi.fn(),
    cancelSubAgent: vi.fn(),
  }),
}))

vi.mock('./context/useSettingsContext', () => ({
  useSettingsContext: () => ({
    settings: {
      provider: 'google',
      model: 'gemini-2.5-pro',
      agentMode: 'orchestrator',
      separateExecutionSurfaces: true,
      autoReturnToChat: false,
      enableReasoning: false,
      reasoningEffort: 'adaptive',
      workflowTemplates: [],
      integrations: [],
      displayName: 'Tester',
    },
    patchSettings: vi.fn(),
    wsConfig: {},
  }),
}))

vi.mock('./hooks/useMicrophone', () => ({
  useMicrophone: () => ({
    isActive: false,
    error: null,
    isSupported: false,
    toggle: vi.fn(),
    stop: vi.fn(),
  }),
}))

vi.mock('./hooks/useConversations', () => ({
  useConversations: () => ({
    conversations: [],
    fetchMessages: vi.fn(async () => []),
    deleteConversation: vi.fn(),
    onNewConversationId: vi.fn(),
  }),
}))

vi.mock('./context/NotificationContext', () => ({
  useNotifications: () => ({ addNotification: vi.fn() }),
}))

vi.mock('./hooks/useToast', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
}))

vi.mock('./components/ScreenView', () => ({
  ScreenView: ({ onExampleClick }: { onExampleClick: (prompt: string) => void }) => (
    <button type='button' onClick={() => onExampleClick('Open the dashboard')}>
      Trigger Example
    </button>
  ),
}))

vi.mock('./components/ActionLog', () => ({
  ActionLog: ({ entries }: { entries: unknown[] }) => <div data-testid='action-log-count'>{entries.length}</div>,
}))

vi.mock('./components/ChatPanel', () => ({
  ChatPanel: ({ serverMessages }: { serverMessages: Array<{ role: string; content: string }> }) => (
    <div>
      <div data-testid='chat-user-bubbles'>
        {serverMessages.filter((m) => m.role === 'user').map((m) => m.content).join(' | ')}
      </div>
    </div>
  ),
}))

vi.mock('./components/UserMenu', () => ({ UserMenu: () => <div /> }))
vi.mock('./components/UsageDropdown', () => ({ UsageDropdown: () => <div /> }))
vi.mock('./components/NotificationBell', () => ({ NotificationBell: () => <div /> }))
vi.mock('./components/SpendingAlert', () => ({ SpendingAlert: () => <div /> }))
vi.mock('./components/WorkflowView', () => ({ WorkflowView: () => <div /> }))
vi.mock('./components/SubAgentPanel', () => ({ SubAgentPanel: () => <div /> }))
vi.mock('./components/TaskPlanView', () => ({ TaskPlanView: () => <div /> }))
vi.mock('./components/AutomationsPage', () => ({ AutomationsPage: () => <div /> }))
vi.mock('./components/settings/SettingsPage', () => ({ SettingsPage: () => <div /> }))
vi.mock('./components/admin/ImpersonationBanner', () => ({ ImpersonationBanner: () => <div /> }))
vi.mock('./components/admin/useImpersonation', () => ({ useImpersonation: () => ({ status: 'inactive', checkStatus: vi.fn() }) }))
vi.mock('./components/OnboardingWizard', () => ({ OnboardingWizard: () => <div />, isOnboardingComplete: () => true }))
vi.mock('./components/ProductTour', () => ({ ProductTour: () => <div />, isTourComplete: () => true }))
vi.mock('./components/LandingPage', () => ({ LandingPage: () => <div /> }))
vi.mock('./components/AuthPage', () => ({ AuthPage: () => <div /> }))
vi.mock('./components/PrivacyPage', () => ({ PrivacyPage: () => <div /> }))
vi.mock('./components/TermsPage', () => ({ TermsPage: () => <div /> }))
vi.mock('./components/UseCasePage', () => ({ UseCasePage: () => <div /> }))
vi.mock('./public/EmbeddedDocsPage', () => ({ EmbeddedDocsPage: () => <div />, slugFromDocsPath: () => null }))
vi.mock('./components/ChangelogModal', () => ({
  ChangelogModal: () => <div />,
  SubAgentModal: () => <div />,
  useChangelog: () => ({ show: false, dismiss: vi.fn(), version: 'test' }),
}))

describe('App browser example click UX', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  beforeEach(() => {
    sendSpy.mockReset()
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/api/auth/me')) {
        return {
          ok: true,
          json: async () => ({ authenticated: true, user: { uid: 'u1', name: 'Test', email: 'test@example.com', role: 'user' } }),
        } as Response
      }
      return { ok: true, json: async () => ({ ok: true }) } as Response
    }))
  })

  it('sends a chat-sourced navigate action, creates a chat user bubble, and avoids action-log noise', async () => {
    const { default: App } = await import('./App')
    render(<App />)

    await screen.findByRole('button', { name: 'Trigger Example' })
    fireEvent.click(screen.getByRole('button', { name: 'Trigger Example' }))

    await waitFor(() => {
      expect(sendSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          action: 'navigate',
          instruction: 'Open the dashboard',
          metadata: expect.objectContaining({
            task_label_source: 'chat',
            task_label: 'Open the dashboard',
          }),
        }),
      )
    })

    expect(screen.getByTestId('action-log-count').textContent).toBe('0')

    fireEvent.click(screen.getByRole('button', { name: /chat/i }))
    await waitFor(() => {
      expect(screen.getByTestId('chat-user-bubbles').textContent).toContain('Open the dashboard')
    })
  })
})
