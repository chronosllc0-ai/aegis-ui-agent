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
    description: 'Search the web and extract page content.',
    enabled: true,
    status: 'connected',
    builtIn: true,
    tools: ['web_search', 'extract_page'],
  },
  {
    id: 'filesystem',
    name: 'File System',
    icon: '📁',
    description: 'Read and write local files and downloads.',
    enabled: false,
    status: 'disabled',
    builtIn: true,
    tools: ['list_files', 'read_file', 'write_file'],
  },
  {
    id: 'code-exec',
    name: 'Code Execution',
    icon: '💻',
    description: 'Run snippets in a sandboxed environment.',
    enabled: false,
    status: 'disabled',
    builtIn: true,
    tools: ['exec_python', 'exec_javascript'],
  },
  {
    id: 'telegram',
    name: 'Telegram',
    icon: '💬',
    description: 'Send and receive Telegram bot messages.',
    enabled: false,
    status: 'disabled',
    tools: ['telegram_get_messages', 'telegram_send_message', 'telegram_send_image', 'telegram_list_chats'],
  },
  {
    id: 'slack',
    name: 'Slack',
    icon: '💬',
    description: 'Post updates and read channel conversations.',
    enabled: false,
    status: 'disabled',
    tools: ['slack_get_messages', 'slack_send_message', 'slack_list_channels', 'slack_send_file'],
  },
  {
    id: 'discord',
    name: 'Discord',
    icon: '💬',
    description: 'Interact with Discord channels and files.',
    enabled: false,
    status: 'disabled',
    tools: ['discord_get_messages', 'discord_send_message', 'discord_list_channels', 'discord_send_file'],
  },
]

export function maskSecret(value: string): string {
  if (!value) return ''
  if (value.length < 8) return '••••••'
  return `${value.slice(0, 3)}••••${value.slice(-3)}`
}
