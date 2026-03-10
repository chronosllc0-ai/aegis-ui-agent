export type AuthType = 'none' | 'api_key' | 'oauth'

export type IntegrationStatus = 'connected' | 'error' | 'disabled'

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
    icon: '🌐',
    description: 'Search the web and extract content.',
    enabled: true,
    status: 'connected',
    builtIn: true,
    tools: ['web_search', 'extract_page'],
  },
  {
    id: 'filesystem',
    name: 'File System',
    icon: '📁',
    description: 'Read/write local files and manage downloads.',
    enabled: false,
    status: 'disabled',
    builtIn: true,
    tools: ['list_files', 'read_file', 'write_file'],
  },
  {
    id: 'code-exec',
    name: 'Code Execution',
    icon: '💻',
    description: 'Execute sandboxed snippets.',
    enabled: false,
    status: 'disabled',
    builtIn: true,
    tools: ['exec_python', 'exec_javascript'],
  },
  {
    id: 'telegram',
    name: 'Telegram',
    icon: '💬',
    description: 'Telegram bot messaging tools.',
    enabled: true,
    status: 'connected',
    tools: ['telegram_get_messages', 'telegram_send_message', 'telegram_send_image', 'telegram_list_chats'],
  },
  {
    id: 'slack',
    name: 'Slack',
    icon: '💬',
    description: 'Slack channels and messaging tools.',
    enabled: false,
    status: 'disabled',
    tools: ['slack_get_messages', 'slack_send_message', 'slack_list_channels', 'slack_send_file'],
  },
  {
    id: 'discord',
    name: 'Discord',
    icon: '💬',
    description: 'Discord guild channels and files.',
    enabled: true,
    status: 'error',
    tools: ['discord_get_messages', 'discord_send_message', 'discord_list_channels', 'discord_send_file'],
  },
]

export function maskSecret(value: string): string {
  if (!value) return ''
  if (value.length < 8) return '••••••'
  return `${value.slice(0, 3)}••••${value.slice(-3)}`
}
