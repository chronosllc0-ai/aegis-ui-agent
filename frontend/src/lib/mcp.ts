export type AuthType = 'none' | 'api_key' | 'oauth'

export type IntegrationStatus = 'connected' | 'error' | 'disabled' | 'needs_auth'

export type IntegrationConfig = {
  id: string
  name: string
  icon: string
  description: string
  enabled: boolean
  status: IntegrationStatus
  builtIn?: boolean
  authType?: AuthType
  serverUrl?: string
  apiKeyMasked?: string
  settings?: Record<string, string>
  tools: string[]
  scopes?: string[]
  lastCheckedAt?: string
  lastUsedAt?: string
}

export type CustomServerForm = {
  serverName: string
  serverUrl: string
  authType: AuthType
  apiKey: string
}

export const DEFAULT_INTEGRATIONS: IntegrationConfig[] = [
  {
    id: 'web-search',
    name: 'Web Search',
    icon: 'web-search',
    description: 'Search the web and extract content.',
    enabled: true,
    status: 'connected',
    builtIn: true,
    tools: ['web_search', 'extract_page'],
    scopes: ['Read internet content'],
    lastCheckedAt: '2026-03-10T17:05:00Z',
    lastUsedAt: '2026-03-10T17:01:00Z',
  },
  {
    id: 'filesystem',
    name: 'File System',
    icon: 'filesystem',
    description: 'Read/write local files and manage downloads.',
    enabled: false,
    status: 'disabled',
    builtIn: true,
    tools: ['list_files', 'read_file', 'write_file'],
    scopes: ['Local workspace'],
    lastCheckedAt: '2026-03-10T16:58:00Z',
  },
  {
    id: 'code-exec',
    name: 'Code Execution',
    icon: 'code-exec',
    description: 'Execute sandboxed snippets.',
    enabled: true,
    status: 'connected',
    builtIn: true,
    tools: ['exec_python', 'exec_javascript'],
    scopes: ['Sandbox runtime'],
    lastCheckedAt: '2026-03-10T17:08:00Z',
    lastUsedAt: '2026-03-10T17:06:00Z',
  },
  {
    id: 'brave-search',
    name: 'Brave Search',
    icon: 'brave-search',
    description: 'Brave Search web results with snippets.',
    enabled: false,
    status: 'needs_auth',
    builtIn: true,
    tools: ['brave.web_search'],
    scopes: ['Search API'],
  },
  {
    id: 'telegram',
    name: 'Telegram',
    icon: 'telegram',
    description: 'Telegram bot messaging tools.',
    enabled: true,
    status: 'connected',
    tools: ['telegram_get_messages', 'telegram_send_message', 'telegram_send_image', 'telegram_list_chats'],
    authType: 'api_key',
    scopes: ['Read chats', 'Send messages', 'Send media'],
    lastCheckedAt: '2026-03-10T17:04:00Z',
    lastUsedAt: '2026-03-10T16:45:00Z',
  },
  {
    id: 'slack',
    name: 'Slack',
    icon: 'slack',
    description: 'Slack channels and messaging tools.',
    enabled: false,
    status: 'needs_auth',
    tools: ['slack_get_messages', 'slack_send_message', 'slack_list_channels', 'slack_send_file'],
    authType: 'oauth',
    scopes: ['Read channels', 'Post messages', 'Upload files'],
    lastCheckedAt: '2026-03-10T17:02:00Z',
  },
  {
    id: 'discord',
    name: 'Discord',
    icon: 'discord',
    description: 'Discord guild channels and files.',
    enabled: true,
    status: 'error',
    tools: ['discord_get_messages', 'discord_send_message', 'discord_list_channels', 'discord_send_file'],
    authType: 'api_key',
    scopes: ['Read channels', 'Send messages'],
    lastCheckedAt: '2026-03-10T17:00:00Z',
    lastUsedAt: '2026-03-09T23:11:00Z',
  },
]

export function maskSecret(value: string): string {
  if (!value) return ''
  if (value.length < 8) return '••••••'
  return `${value.slice(0, 3)}••••${value.slice(-3)}`
}
