import { createElement } from 'react'
import type { IconType } from 'react-icons'
import { FaDiscord, FaFolder, FaGithub, FaGlobe, FaLock, FaPlus, FaSlack, FaTelegram, FaTerminal } from 'react-icons/fa'

export type AuthType = 'none' | 'api_key' | 'oauth'

export type IntegrationStatus = 'connected' | 'error' | 'disabled'
export type IntegrationIcon = 'web-search' | 'filesystem' | 'code-exec' | 'telegram' | 'slack' | 'discord' | 'github' | 'custom'

export type IntegrationConfig = {
  id: string
  name: string
  icon: IntegrationIcon
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

export const GITHUB_PAT_INTEGRATION_ID = 'github-pat'

/* react-icons map used as fallback for generic tool icons */
const INTEGRATION_ICON_MAP: Record<IntegrationIcon, IconType> = {
  'web-search': FaGlobe,
  filesystem: FaFolder,
  'code-exec': FaTerminal,
  telegram: FaTelegram,
  slack: FaSlack,
  discord: FaDiscord,
  github: FaGithub,
  custom: FaPlus,
}

/* Hosted brand images - used for platform icons so the correct logo always shows */
const PLATFORM_IMAGE_URL: Record<string, string> = {
  telegram: 'https://upload.wikimedia.org/wikipedia/commons/8/82/Telegram_logo.svg',
  discord: 'https://cdn.prod.website-files.com/6257adef93867e50d84d30e2/636e0a69f118df70ad7828d4_icon_clyde_blurple_RGB.svg',
  slack: 'https://a.slack-edge.com/80588/marketing/img/icons/icon_slack_hash_colored.png',
  github: 'https://github.githubassets.com/images/modules/logos_page/GitHub-Mark.png',
}

const LEGACY_INTEGRATION_ICON_MAP: Record<string, IntegrationIcon> = {
  '🌐': 'web-search',
  '📁': 'filesystem',
  '💻': 'code-exec',
  '💬': 'slack',
  '➕': 'custom',
}

export const DEFAULT_INTEGRATIONS: IntegrationConfig[] = [
  {
    id: 'web-search',
    name: 'Web Search',
    icon: 'web-search',
    description: 'Search the web and extract content.',
    enabled: false,
    status: 'disabled',
    builtIn: true,
    tools: ['web_search', 'extract_page'],
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
  },
  {
    id: 'code-exec',
    name: 'Code Execution',
    icon: 'code-exec',
    description: 'Execute sandboxed snippets.',
    enabled: false,
    status: 'disabled',
    builtIn: true,
    tools: ['exec_python', 'exec_javascript'],
  },
  {
    id: 'telegram',
    name: 'Telegram',
    icon: 'telegram',
    description: 'Telegram bot messaging tools.',
    enabled: false,
    status: 'disabled',
    settings: {
      bot_token: '',
      delivery_mode: 'polling',
      webhook_url: '',
      webhook_secret: '',
    },
    tools: ['telegram_get_messages', 'telegram_send_message', 'telegram_send_image', 'telegram_list_chats'],
  },
  {
    id: 'slack',
    name: 'Slack',
    icon: 'slack',
    description: 'Slack channels and messaging tools.',
    enabled: false,
    status: 'disabled',
    settings: {
      bot_token: '',
      oauth_token: '',
      workspace: '',
    },
    tools: ['slack_get_messages', 'slack_send_message', 'slack_list_channels', 'slack_send_file'],
  },
  {
    id: 'discord',
    name: 'Discord',
    icon: 'discord',
    description: 'Discord guild channels and files.',
    enabled: false,
    status: 'disabled',
    settings: {
      bot_token: '',
      guild_id: '',
    },
    tools: ['discord_get_messages', 'discord_send_message', 'discord_list_channels', 'discord_send_file'],
  },
  {
    id: GITHUB_PAT_INTEGRATION_ID,
    name: 'GitHub PAT',
    icon: 'github',
    description: 'GitHub repos, issues, PRs, and webhook events via a personal access token.',
    enabled: false,
    status: 'disabled',
    settings: {
      token: '',
      webhook_secret: '',
      app_id: '',
    },
    tools: ['github_list_repos', 'github_get_issues', 'github_create_issue', 'github_get_pull_requests', 'github_create_comment', 'github_get_file', 'github_clone_repo', 'github_create_branch', 'github_repo_status', 'github_repo_diff', 'github_commit_changes', 'github_push_branch', 'github_create_pull_request', 'github_webhook_event'],
  },
]

function isIntegrationIcon(value: string): value is IntegrationIcon {
  return value in INTEGRATION_ICON_MAP
}

function canonicalIntegrationId(id: string): string {
  return id === 'github' ? GITHUB_PAT_INTEGRATION_ID : id
}

function integrationIconFallback(id: string): IntegrationIcon {
  switch (canonicalIntegrationId(id)) {
    case 'telegram':
      return 'telegram'
    case 'discord':
      return 'discord'
    case 'slack':
      return 'slack'
    case GITHUB_PAT_INTEGRATION_ID:
      return 'github'
    default:
      return 'custom'
  }
}

function mergeIntegrationSettings(
  defaults: Record<string, string> | undefined,
  current: Record<string, string> | undefined,
): Record<string, string> | undefined {
  if (!defaults && !current) return undefined
  return {
    ...(defaults ?? {}),
    ...(current ?? {}),
  }
}

export function normalizeIntegrationIcon(icon: string, fallback: IntegrationIcon = 'custom'): IntegrationIcon {
  if (!icon) return fallback
  if (isIntegrationIcon(icon)) return icon
  return LEGACY_INTEGRATION_ICON_MAP[icon] ?? fallback
}

export function normalizeIntegrationConfig(integration: IntegrationConfig): IntegrationConfig {
  const normalizedId = canonicalIntegrationId(integration.id)
  const defaults = DEFAULT_INTEGRATIONS.find((entry) => entry.id === normalizedId)

  return {
    ...defaults,
    ...integration,
    id: normalizedId,
    name: integration.name || defaults?.name || normalizedId,
    description: integration.description || defaults?.description || '',
    icon: normalizeIntegrationIcon(integration.icon, defaults?.icon ?? integrationIconFallback(normalizedId)),
    settings: mergeIntegrationSettings(defaults?.settings, integration.settings),
    tools: Array.isArray(integration.tools) && integration.tools.length > 0 ? integration.tools : (defaults?.tools ?? []),
  }
}

export function mergeIntegrationCatalog(storedIntegrations: IntegrationConfig[] | undefined): IntegrationConfig[] {
  const stored = Array.isArray(storedIntegrations)
    ? storedIntegrations.map((integration) => normalizeIntegrationConfig(integration))
    : []

  const storedById = new Map(stored.map((integration) => [integration.id, integration]))
  const defaultIds = new Set(DEFAULT_INTEGRATIONS.map((integration) => integration.id))

  const mergedDefaults = DEFAULT_INTEGRATIONS.map((integration) => {
    const normalizedDefault = normalizeIntegrationConfig(integration)
    const storedMatch = storedById.get(normalizedDefault.id)

    if (!storedMatch) return normalizedDefault

    return normalizeIntegrationConfig({
      ...normalizedDefault,
      ...storedMatch,
      settings: mergeIntegrationSettings(normalizedDefault.settings, storedMatch.settings),
      tools: storedMatch.tools.length > 0 ? storedMatch.tools : normalizedDefault.tools,
    })
  })

  const customIntegrations = stored.filter((integration) => !defaultIds.has(integration.id))
  return [...mergedDefaults, ...customIntegrations]
}

export function renderIntegrationIcon(icon: string, className = 'h-4 w-4') {
  const normalized = normalizeIntegrationIcon(icon)
  const resolved = isIntegrationIcon(normalized) ? normalized : 'custom'

  /* Use hosted brand images for platform icons so the correct logo always shows */
  const imgUrl = PLATFORM_IMAGE_URL[resolved]
  if (imgUrl) {
    return createElement('img', { src: imgUrl, alt: resolved, className: `${className} object-contain`, 'aria-hidden': 'true' })
  }

  return createElement(INTEGRATION_ICON_MAP[resolved] ?? FaLock, { className, 'aria-hidden': 'true' })
}

export function maskSecret(value: string): string {
  if (!value) return ''
  if (value.length < 8) return '••••••'
  return `${value.slice(0, 3)}••••${value.slice(-3)}`
}
