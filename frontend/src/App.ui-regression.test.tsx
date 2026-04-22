import { cleanup, render, screen } from '@testing-library/react'
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
    clearFrameCache: vi.fn(),
    activeTaskIdRef: { current: 'idle' },
    activeConversationId: null,
    reasoningMap: {},
    subAgents: [],
    subAgentSteps: {},
    messageSubAgent: vi.fn(),
    cancelSubAgent: vi.fn(),
    activityStatusLabel: '',
    activityDetail: '',
    isActivityVisible: false,
    handoffActive: false,
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
      reasoningEffort: 'medium',
      workflowTemplates: [],
      integrations: [],
      displayName: 'Tester',
      steeringMode: 'auto',
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
    onNewConversationId: vi.fn(),
  }),
}))

vi.mock('./hooks/useSessions', () => ({
  useSessions: () => ({
    sessions: [],
    fetchMessages: vi.fn(async () => []),
    fetchSessions: vi.fn(async () => []),
  }),
}))

vi.mock('./context/NotificationContext', () => ({
  useNotifications: () => ({ addNotification: vi.fn() }),
}))

vi.mock('./hooks/useToast', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
}))

vi.mock('./components/ScreenView', () => ({
  ScreenView: () => <div />,
}))

vi.mock('./components/ActionLog', () => ({
  ActionLog: ({ entries }: { entries: unknown[] }) => <div data-testid='action-log-count'>{entries.length}</div>,
}))

vi.mock('./components/ChatPanel', () => ({
  ChatPanel: () => <div data-testid='chat-panel' />,
}))

vi.mock('./components/settings/StandaloneSettingsPage', () => ({
  StandaloneSettingsPage: ({ tab }: { tab: string }) => <div data-testid='standalone-settings-tab'>{tab}</div>,
}))

vi.mock('./components/settings/SettingsPage', () => ({ SettingsPage: () => <div data-testid='legacy-settings-page' /> }))
vi.mock('./components/UserMenu', () => ({ UserMenu: () => <div /> }))
vi.mock('./components/UsageDropdown', () => ({ UsageDropdown: () => <div /> }))
vi.mock('./components/NotificationBell', () => ({ NotificationBell: () => <div /> }))
vi.mock('./components/SpendingAlert', () => ({ SpendingAlert: () => <div /> }))
vi.mock('./components/WorkflowView', () => ({ WorkflowView: () => <div /> }))
vi.mock('./components/SubAgentPanel', () => ({ SubAgentPanel: () => <div /> }))
vi.mock('./components/TaskPlanView', () => ({ TaskPlanView: () => <div /> }))
vi.mock('./components/AutomationsPage', () => ({ AutomationsPage: () => <div data-testid='automations-page' /> }))
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

describe('App UI regression guards (shell + nav)', () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    window.history.pushState({}, '', '/')
  })

  beforeEach(() => {
    vi.resetModules()
    sendSpy.mockReset()
    window.history.pushState({}, '', '/settings/connections')
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

  it('keeps moved tab-header routing on standalone settings tabs and does not fall back to legacy settings shell', async () => {
    const { default: App } = await import('./App')
    render(<App />)

    await screen.findByTestId('standalone-settings-tab')
    expect(screen.getByTestId('standalone-settings-tab')).toHaveTextContent('Connections')
    expect(screen.queryByTestId('legacy-settings-page')).not.toBeInTheDocument()
  })

  it('maintains sidebar active/inactive state class rules', async () => {
    const { default: App } = await import('./App')
    render(<App />)

    await screen.findByRole('button', { name: /^connections$/i })

    const activeConnections = screen.getAllByRole('button', { name: /^connections$/i })[0]
    const inactiveChat = screen.getAllByRole('button', { name: /^chat$/i })[0]

    expect(activeConnections.className).toContain('bg-[var(--ds-accent-soft)]')
    expect(activeConnections.className).toContain('shadow-[var(--ds-shadow-soft)]')
    expect(inactiveChat.className).toContain('hover:bg-[var(--ds-surface-3)]/45')
    expect(inactiveChat.className).not.toContain('bg-[var(--ds-accent-soft)]')

  })


  it.each([
    { path: '/', expectedTestId: 'chat-panel', expectedText: null },
    { path: '/automations', expectedTestId: 'automations-page', expectedText: null },
    { path: '/settings/connections', expectedTestId: 'standalone-settings-tab', expectedText: 'Connections' },
    { path: '/settings/observability', expectedTestId: 'standalone-settings-tab', expectedText: 'Observability' },
  ])('keeps mobile route rendering stable for $path', async ({ path, expectedTestId, expectedText }) => {
    window.history.pushState({}, '', path)
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 390 })
    window.dispatchEvent(new Event('resize'))

    const { default: App } = await import('./App')
    render(<App />)

    const surface = await screen.findByTestId(expectedTestId)
    if (expectedText) {
      expect(surface).toHaveTextContent(expectedText)
    }
  })

  it('keeps the topbar in a single-row flex shell for title and controls', async () => {
    const { default: App } = await import('./App')
    const { container } = render(<App />)

    await screen.findByRole('heading', { name: 'Aegis' })

    const header = container.querySelector('header')
    expect(header).toBeTruthy()
    const shellRow = header?.querySelector('div.flex.min-h-11.items-center.justify-between.gap-2')
    expect(shellRow).toBeTruthy()
  })
})
