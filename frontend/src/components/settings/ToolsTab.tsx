/**
 * ToolsTab — unified tool permission centre.
 *
 * Every tool exposed by the agent (system browser tools, built-in integrations,
 * bot tokens, OAuth connectors, and future MCP servers) surfaces here. Each tool
 * can be:
 *   • Toggled on/off  (disabled_tools list)
 *   • Scoped to Auto-run  — agent calls it without asking (default)
 *   • Scoped to Confirm   — agent sends an approval card in Chat before running
 *
 * When a tool is set to "Confirm", the ChatPanel renders an ApprovalCard with
 * green Approve / red Reject buttons before the agent proceeds.
 * In Slack/Telegram/Discord bot channels the confirmation is sent there instead.
 */

import { useState, useMemo, useEffect, type ReactElement } from 'react'
import type { AppSettings, ToolPermission } from '../../hooks/useSettings'
import { apiUrl } from '../../lib/api'

// ── Tool catalogue ────────────────────────────────────────────────────────────

export type ToolCategory = {
  id: string
  label: string
  icon: string
  description: string
  tools: ToolDef[]
  /** When false the whole category cannot be disabled (always-on system tools). */
  canDisable?: boolean
}

export type ToolDef = {
  id: string
  name: string
  description: string
  risk: 'low' | 'medium' | 'high'
  defaultPermission: ToolPermission
}

// System browser-control tools — always present, no auth required
const BROWSER_TOOLS: ToolDef[] = [
  { id: 'screenshot',   name: 'Screenshot',      description: 'Capture the current browser viewport', risk: 'low',    defaultPermission: 'auto' },
  { id: 'go_to_url',    name: 'Navigate',         description: 'Navigate to a URL',                    risk: 'low',    defaultPermission: 'auto' },
  { id: 'click',        name: 'Click',            description: 'Click an element on the page',          risk: 'low',    defaultPermission: 'auto' },
  { id: 'type_text',    name: 'Type Text',        description: 'Type text into a focused element',      risk: 'low',    defaultPermission: 'auto' },
  { id: 'scroll',       name: 'Scroll',           description: 'Scroll the page',                       risk: 'low',    defaultPermission: 'auto' },
  { id: 'wait',         name: 'Wait',             description: 'Pause execution briefly',               risk: 'low',    defaultPermission: 'auto' },
  { id: 'extract_data', name: 'Extract Data',     description: 'Extract structured data from the page', risk: 'low',    defaultPermission: 'auto' },
]

const WEB_TOOLS: ToolDef[] = [
  { id: 'web_search',   name: 'Web Search',       description: 'Search the web via a search engine',    risk: 'low',    defaultPermission: 'auto' },
  { id: 'extract_page', name: 'Extract Page',     description: 'Fetch & parse a URL',                   risk: 'low',    defaultPermission: 'auto' },
]

const FILESYSTEM_TOOLS: ToolDef[] = [
  { id: 'list_files',   name: 'List Files',       description: 'List directory contents',               risk: 'low',    defaultPermission: 'auto' },
  { id: 'read_file',    name: 'Read File',         description: 'Read a file from disk',                 risk: 'medium', defaultPermission: 'auto' },
  { id: 'write_file',   name: 'Write File',        description: 'Write or overwrite a file',             risk: 'high',   defaultPermission: 'confirm' },
]

const CODE_TOOLS: ToolDef[] = [
  { id: 'exec_python',     name: 'Run Python',     description: 'Execute Python code in a sandbox',     risk: 'high',   defaultPermission: 'confirm' },
  { id: 'exec_javascript', name: 'Run JavaScript', description: 'Execute JS code in a sandbox',         risk: 'high',   defaultPermission: 'confirm' },
]

const TELEGRAM_TOOLS: ToolDef[] = [
  { id: 'telegram_get_messages',  name: 'Read Messages',  description: 'Read Telegram messages',          risk: 'low',    defaultPermission: 'auto' },
  { id: 'telegram_send_message',  name: 'Send Message',   description: 'Send a Telegram message',         risk: 'medium', defaultPermission: 'confirm' },
  { id: 'telegram_send_image',    name: 'Send Image',     description: 'Send an image via Telegram',      risk: 'medium', defaultPermission: 'confirm' },
  { id: 'telegram_list_chats',    name: 'List Chats',     description: 'List Telegram chats/channels',    risk: 'low',    defaultPermission: 'auto' },
]

const SLACK_BOT_TOOLS: ToolDef[] = [
  { id: 'slack_get_messages',   name: 'Read Messages',  description: 'Read Slack messages',              risk: 'low',    defaultPermission: 'auto' },
  { id: 'slack_send_message',   name: 'Send Message',   description: 'Send a Slack message',             risk: 'medium', defaultPermission: 'confirm' },
  { id: 'slack_list_channels',  name: 'List Channels',  description: 'List Slack channels',              risk: 'low',    defaultPermission: 'auto' },
  { id: 'slack_send_file',      name: 'Send File',      description: 'Upload a file to Slack',           risk: 'medium', defaultPermission: 'confirm' },
]

const DISCORD_TOOLS: ToolDef[] = [
  { id: 'discord_get_messages',  name: 'Read Messages',  description: 'Read Discord messages',           risk: 'low',    defaultPermission: 'auto' },
  { id: 'discord_send_message',  name: 'Send Message',   description: 'Send a Discord message',          risk: 'medium', defaultPermission: 'confirm' },
  { id: 'discord_list_channels', name: 'List Channels',  description: 'List Discord channels',           risk: 'low',    defaultPermission: 'auto' },
  { id: 'discord_send_file',     name: 'Send File',      description: 'Upload a file to Discord',        risk: 'medium', defaultPermission: 'confirm' },
]

const GITHUB_BOT_TOOLS: ToolDef[] = [
  { id: 'github_list_repos',        name: 'List Repos',       description: 'List repositories',              risk: 'low',    defaultPermission: 'auto' },
  { id: 'github_get_issues',        name: 'Get Issues',       description: 'Fetch issues from a repo',       risk: 'low',    defaultPermission: 'auto' },
  { id: 'github_create_issue',      name: 'Create Issue',     description: 'Open a new GitHub issue',        risk: 'medium', defaultPermission: 'confirm' },
  { id: 'github_get_pull_requests', name: 'Get PRs',          description: 'Fetch pull requests',            risk: 'low',    defaultPermission: 'auto' },
  { id: 'github_create_comment',    name: 'Create Comment',   description: 'Post a comment on PR or issue',  risk: 'medium', defaultPermission: 'confirm' },
  { id: 'github_get_file',          name: 'Get File',         description: 'Read a file from a repo',        risk: 'low',    defaultPermission: 'auto' },
  { id: 'github_webhook_event',     name: 'Webhook Event',    description: 'Receive incoming webhook events', risk: 'low',    defaultPermission: 'auto' },
]

const MEMORY_TOOLS: ToolDef[] = [
  { id: 'memory_search', name: 'Memory Search',  description: 'Semantic search through stored memories',           risk: 'low',    defaultPermission: 'auto' },
  { id: 'memory_write',  name: 'Memory Write',   description: 'Store a new memory entry',                         risk: 'medium', defaultPermission: 'auto' },
  { id: 'memory_read',   name: 'Memory Read',    description: 'Read a specific memory entry by ID',               risk: 'low',    defaultPermission: 'auto' },
  { id: 'memory_patch',  name: 'Memory Patch',   description: 'Update an existing memory entry',                  risk: 'medium', defaultPermission: 'auto' },
]

const AGENT_INTERACTION_TOOLS: ToolDef[] = [
  { id: 'ask_user_input',  name: 'Ask User Input',  description: 'Pause and ask the user a question mid-task',       risk: 'low',    defaultPermission: 'auto' },
  { id: 'summarize_task',  name: 'Summarize Task',  description: 'Generate a structured summary of completed work',  risk: 'low',    defaultPermission: 'auto' },
  { id: 'confirm_plan',    name: 'Confirm Plan',    description: 'Present a plan for user approval before executing', risk: 'low',    defaultPermission: 'auto' },
]

const CRON_TOOLS: ToolDef[] = [
  { id: 'cron_write',  name: 'Create Automation', description: 'Create a new scheduled automation task',           risk: 'medium', defaultPermission: 'confirm' },
  { id: 'cron_patch',  name: 'Edit Automation',   description: 'Modify an existing scheduled automation',          risk: 'medium', defaultPermission: 'confirm' },
  { id: 'cron_delete', name: 'Delete Automation', description: 'Permanently delete a scheduled automation',        risk: 'high',   defaultPermission: 'confirm' },
]

// OAuth connector tools come from the backend /api/connectors/:id/actions endpoint.
// We define the well-known ones here so they display immediately; dynamic ones
// fetched from the server are merged in at runtime.

// ── Category icon SVGs — no emoji ─────────────────────────────────────────────
// Each returns a small inline SVG element sized to fit the 20×20 slot in CategorySection header.
export const CATEGORY_ICONS: Record<string, ReactElement> = {
  browser: (
    <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2' strokeLinecap='round' strokeLinejoin='round' className='h-5 w-5 text-zinc-300'>
      <circle cx='12' cy='12' r='10'/><path d='M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z'/>
    </svg>
  ),
  'agent-interaction': (
    <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2' strokeLinecap='round' strokeLinejoin='round' className='h-5 w-5 text-zinc-300'>
      <path d='M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z'/>
    </svg>
  ),
  memory: (
    <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2' strokeLinecap='round' strokeLinejoin='round' className='h-5 w-5 text-zinc-300'>
      <path d='M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96-.44 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24 2.5 2.5 0 0 1 1.98-3A2.5 2.5 0 0 1 9.5 2Z'/>
      <path d='M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96-.44 2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24 2.5 2.5 0 0 0-1.98-3A2.5 2.5 0 0 0 14.5 2Z'/>
    </svg>
  ),
  cron: (
    <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2' strokeLinecap='round' strokeLinejoin='round' className='h-5 w-5 text-zinc-300'>
      <circle cx='12' cy='12' r='10'/><path d='M12 6v6l4 2'/>
    </svg>
  ),
  'web-search': (
    <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2' strokeLinecap='round' strokeLinejoin='round' className='h-5 w-5 text-zinc-300'>
      <circle cx='11' cy='11' r='8'/><path d='m21 21-4.35-4.35'/>
    </svg>
  ),
  filesystem: (
    <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2' strokeLinecap='round' strokeLinejoin='round' className='h-5 w-5 text-zinc-300'>
      <path d='M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z'/>
    </svg>
  ),
  'code-exec': (
    <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2' strokeLinecap='round' strokeLinejoin='round' className='h-5 w-5 text-zinc-300'>
      <polyline points='16 18 22 12 16 6'/><polyline points='8 6 2 12 8 18'/>
    </svg>
  ),
  telegram: (
    // Telegram paper-plane icon
    <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2' strokeLinecap='round' strokeLinejoin='round' className='h-5 w-5 text-zinc-300'>
      <path d='M22 2 11 13'/><path d='M22 2 15 22 11 13 2 9l20-7z'/>
    </svg>
  ),
  'slack-bot': (
    // Slack hash icon (closest neutral SVG without brand color)
    <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2' strokeLinecap='round' strokeLinejoin='round' className='h-5 w-5 text-zinc-300'>
      <line x1='4' y1='9' x2='20' y2='9'/><line x1='4' y1='15' x2='20' y2='15'/>
      <line x1='10' y1='3' x2='8' y2='21'/><line x1='16' y1='3' x2='14' y2='21'/>
    </svg>
  ),
  discord: (
    // Game controller / headset icon for Discord
    <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2' strokeLinecap='round' strokeLinejoin='round' className='h-5 w-5 text-zinc-300'>
      <path d='M9 10h.01M15 10h.01M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 14c-2.67 0-8-1.34-8-4v-1.26C5.23 9.3 7 8 9 8c1.35 0 2.55.5 3 1h0c.45-.5 1.65-1 3-1 2 0 3.77 1.3 5 2.74V12c0 2.66-5.33 4-8 4z'/>
    </svg>
  ),
  'github-bot': (
    // Git branch icon for GitHub
    <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2' strokeLinecap='round' strokeLinejoin='round' className='h-5 w-5 text-zinc-300'>
      <line x1='6' y1='3' x2='6' y2='15'/><circle cx='18' cy='6' r='3'/><circle cx='6' cy='18' r='3'/><path d='M18 9a9 9 0 0 1-9 9'/>
    </svg>
  ),
}

// Fallback SVG for unknown category IDs (OAuth connectors etc.)
const FallbackCategoryIcon = () => (
  <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2' strokeLinecap='round' strokeLinejoin='round' className='h-5 w-5 text-zinc-300'>
    <path d='M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71'/>
    <path d='M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71'/>
  </svg>
)

export const STATIC_TOOL_CATEGORIES: ToolCategory[] = [
  {
    id: 'browser',
    label: 'Browser Control',
    icon: 'browser',
    description: 'Core browser automation — navigate, click, type, screenshot. Always available.',
    canDisable: true,
    tools: BROWSER_TOOLS,
  },
  {
    id: 'agent-interaction',
    label: 'Agent Interaction',
    icon: 'agent-interaction',
    description: 'Tools for agent–human collaboration: asking questions, confirming plans, and summarizing work.',
    canDisable: true,
    tools: AGENT_INTERACTION_TOOLS,
  },
  {
    id: 'memory',
    label: 'Memory',
    icon: 'memory',
    description: 'Read, write, search, and update the agent\'s persistent memory store.',
    canDisable: true,
    tools: MEMORY_TOOLS,
  },
  {
    id: 'cron',
    label: 'Automations (Cron)',
    icon: 'cron',
    description: 'Create, edit, and delete scheduled automation tasks programmatically.',
    canDisable: true,
    tools: CRON_TOOLS,
  },
  {
    id: 'web-search',
    label: 'Web Search',
    icon: 'web-search',
    description: 'Search the internet and extract page content.',
    canDisable: true,
    tools: WEB_TOOLS,
  },
  {
    id: 'filesystem',
    label: 'File System',
    icon: 'filesystem',
    description: 'Read and write local files.',
    canDisable: true,
    tools: FILESYSTEM_TOOLS,
  },
  {
    id: 'code-exec',
    label: 'Code Execution',
    icon: 'code-exec',
    description: 'Run Python and JavaScript in a sandbox.',
    canDisable: true,
    tools: CODE_TOOLS,
  },
  {
    id: 'telegram',
    label: 'Telegram Bot',
    icon: 'telegram',
    description: 'Send and receive messages via your Telegram bot.',
    canDisable: true,
    tools: TELEGRAM_TOOLS,
  },
  {
    id: 'slack-bot',
    label: 'Slack Bot',
    icon: 'slack-bot',
    description: 'Interact with Slack workspaces via your bot token.',
    canDisable: true,
    tools: SLACK_BOT_TOOLS,
  },
  {
    id: 'discord',
    label: 'Discord Bot',
    icon: 'discord',
    description: 'Interact with Discord servers via your bot.',
    canDisable: true,
    tools: DISCORD_TOOLS,
  },
  {
    id: 'github-bot',
    label: 'GitHub (Bot Token)',
    icon: 'github-bot',
    description: 'Manage repos, issues, and PRs via a personal access token.',
    canDisable: true,
    tools: GITHUB_BOT_TOOLS,
  },
]

// ── Risk badge ────────────────────────────────────────────────────────────────

function RiskBadge({ risk }: { risk: 'low' | 'medium' | 'high' }) {
  const cls =
    risk === 'low'    ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' :
    risk === 'medium' ? 'bg-amber-500/10 text-amber-400 border-amber-500/20' :
                        'bg-red-500/10 text-red-400 border-red-500/20'
  return (
    <span className={`rounded border px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wide ${cls}`}>
      {risk}
    </span>
  )
}

// ── Toggle switch ─────────────────────────────────────────────────────────────

function Toggle({ checked, onToggle, disabled }: { checked: boolean; onToggle: () => void; disabled?: boolean }) {
  return (
    <button
      type='button'
      role='switch'
      aria-checked={checked}
      onClick={onToggle}
      disabled={disabled}
      className={`relative h-5 w-9 shrink-0 rounded-full border transition-colors ${
        disabled ? 'cursor-not-allowed opacity-40' :
        checked   ? 'border-blue-500/60 bg-blue-600' : 'border-[#3a3a3a] bg-[#2a2a2a]'
      }`}
    >
      <span
        className={`absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform ${
          checked ? 'translate-x-4' : 'translate-x-0'
        }`}
      />
    </button>
  )
}

// ── Permission selector ───────────────────────────────────────────────────────

function PermissionSelect({
  value,
  onChange,
  disabled,
}: {
  value: ToolPermission
  onChange: (v: ToolPermission) => void
  disabled?: boolean
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value as ToolPermission)}
      disabled={disabled}
      className='rounded-lg border border-[#2a2a2a] bg-[#1a1a1a] py-1 pl-2 pr-7 text-xs text-zinc-300 outline-none focus:border-blue-500/60 disabled:opacity-40 disabled:cursor-not-allowed'
    >
      <option value='auto'>Run automatically</option>
      <option value='confirm'>Ask for confirmation</option>
    </select>
  )
}

// ── Single tool row ───────────────────────────────────────────────────────────

function ToolRow({
  tool,
  enabled,
  permission,
  onToggle,
  onPermissionChange,
}: {
  tool: ToolDef
  enabled: boolean
  permission: ToolPermission
  onToggle: () => void
  onPermissionChange: (p: ToolPermission) => void
}) {
  return (
    <div className={`flex items-center gap-3 rounded-xl border px-3 py-2.5 transition-colors ${
      enabled ? 'border-[#2a2a2a] bg-[#141414]' : 'border-[#1e1e1e] bg-[#0f0f0f] opacity-60'
    }`}>
      {/* Toggle */}
      <Toggle checked={enabled} onToggle={onToggle} />

      {/* Info */}
      <div className='min-w-0 flex-1'>
        <div className='flex items-center gap-1.5 flex-wrap'>
          <span className='text-xs font-medium text-zinc-200'>{tool.name}</span>
          <RiskBadge risk={tool.risk} />
        </div>
        <p className='text-[10px] text-zinc-500 leading-snug mt-0.5'>{tool.description}</p>
      </div>

      {/* Permission selector — only shown when tool is enabled */}
      {enabled && (
        <PermissionSelect value={permission} onChange={onPermissionChange} />
      )}
    </div>
  )
}

// ── Category section ──────────────────────────────────────────────────────────

function CategorySection({
  category,
  toolPermissions,
  disabledTools,
  onToolToggle,
  onPermissionChange,
  connectorActions,
}: {
  category: ToolCategory
  toolPermissions: Record<string, ToolPermission>
  disabledTools: string[]
  onToolToggle: (toolId: string) => void
  onPermissionChange: (toolId: string, p: ToolPermission) => void
  connectorActions?: ConnectorAction[]
}) {
  const [expanded, setExpanded] = useState(true)

  // Merge static tool defs with any dynamic connector actions
  const allTools: ToolDef[] = useMemo(() => {
    const base = [...category.tools]
    if (connectorActions) {
      for (const a of connectorActions) {
        if (!base.find((t) => t.id === a.id)) {
          base.push({
            id: a.id,
            name: a.name,
            description: a.description,
            risk: 'medium',
            defaultPermission: 'auto',
          })
        }
      }
    }
    return base
  }, [category.tools, connectorActions])

  const enabledCount = allTools.filter((t) => !disabledTools.includes(t.id)).length
  const confirmCount = allTools.filter((t) => {
    const perm = toolPermissions[t.id] ?? t.defaultPermission
    return perm === 'confirm' && !disabledTools.includes(t.id)
  }).length

  return (
    <div className='rounded-2xl border border-[#2a2a2a] bg-[#111] overflow-hidden'>
      {/* Header */}
      <button
        type='button'
        onClick={() => setExpanded((v) => !v)}
        className='w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-[#1a1a1a] transition-colors'
      >
        <span className='flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[#2a2a2a]'>
          {/* icon is either a CATEGORY_ICONS key (SVG) or a URL string for OAuth connectors */}
          {category.icon.startsWith('http') ? (
            <img src={category.icon} alt={category.label} className='h-5 w-5 rounded object-contain' onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }} />
          ) : (
            CATEGORY_ICONS[category.icon] ?? <FallbackCategoryIcon />
          )}
        </span>
        <div className='min-w-0 flex-1'>
          <div className='flex items-center gap-2'>
            <span className='text-sm font-semibold text-zinc-100'>{category.label}</span>
            <span className='text-[10px] text-zinc-500'>
              {enabledCount}/{allTools.length} active
              {confirmCount > 0 && ` · ${confirmCount} need confirmation`}
            </span>
          </div>
          <p className='text-[11px] text-zinc-500 leading-snug'>{category.description}</p>
        </div>
        <svg
          className={`h-4 w-4 shrink-0 text-zinc-500 transition-transform ${expanded ? 'rotate-180' : ''}`}
          fill='none' viewBox='0 0 24 24' stroke='currentColor' strokeWidth={2}
        >
          <path strokeLinecap='round' strokeLinejoin='round' d='m19 9-7 7-7-7' />
        </svg>
      </button>

      {/* Tool rows */}
      {expanded && (
        <div className='border-t border-[#2a2a2a] px-4 py-3 space-y-2'>
          {allTools.map((tool) => {
            const isEnabled = !disabledTools.includes(tool.id)
            const perm = toolPermissions[tool.id] ?? tool.defaultPermission
            return (
              <ToolRow
                key={tool.id}
                tool={tool}
                enabled={isEnabled}
                permission={perm}
                onToggle={() => onToolToggle(tool.id)}
                onPermissionChange={(p) => onPermissionChange(tool.id, p)}
              />
            )
          })}
        </div>
      )}
    </div>
  )
}

// ── OAuth connector action type (from backend) ────────────────────────────────

type ConnectorAction = {
  id: string
  name: string
  description: string
  parameters: Record<string, string>
  category: string
}

type ConnectorMeta = {
  id: string
  name: string
  description: string
  icon: string
  connected: boolean
  configured: boolean
  status: string
}

// ── Main ToolsTab ─────────────────────────────────────────────────────────────

type ToolsTabProps = {
  settings: AppSettings
  onPatch: (next: Partial<AppSettings>) => void
}

export function ToolsTab({ settings, onPatch }: ToolsTabProps) {
  const [search, setSearch] = useState('')
  const [connectors, setConnectors] = useState<ConnectorMeta[]>([])
  const [connectorActions, setConnectorActions] = useState<Record<string, ConnectorAction[]>>({})
  const [loadingConnectors, setLoadingConnectors] = useState(true)

  // Fetch connected OAuth connectors + their actions
  useEffect(() => {
    void (async () => {
      try {
        const r = await fetch(apiUrl('/api/connectors'), { credentials: 'include' })
        const d = await r.json()
        if (d.ok) {
          const active = (d.connectors as ConnectorMeta[]).filter(
            (c) => c.connected && c.status === 'active'
          )
          setConnectors(active)
          // Fetch actions for each active connector
          const actionsMap: Record<string, ConnectorAction[]> = {}
          await Promise.all(
            active.map(async (c) => {
              try {
                const ar = await fetch(apiUrl(`/api/connectors/${c.id}/actions`), { credentials: 'include' })
                const ad = await ar.json()
                if (ad.ok) actionsMap[c.id] = ad.actions
              } catch { /* silent */ }
            })
          )
          setConnectorActions(actionsMap)
        }
      } catch { /* silent */ }
      finally { setLoadingConnectors(false) }
    })()
  }, [])

  const toolPermissions = settings.toolPermissions ?? {}
  const disabledTools   = settings.disabledTools   ?? []

  const handleToolToggle = (toolId: string) => {
    const next = disabledTools.includes(toolId)
      ? disabledTools.filter((id) => id !== toolId)
      : [...disabledTools, toolId]
    onPatch({ disabledTools: next })
  }

  const handlePermissionChange = (toolId: string, perm: ToolPermission) => {
    onPatch({ toolPermissions: { ...toolPermissions, [toolId]: perm } })
  }

  // Build connector categories from active OAuth connectors
  const connectorCategories: ToolCategory[] = useMemo(() => {
    return connectors.map((c) => ({
      id: `connector-${c.id}`,
      label: c.name,
      icon: c.icon || 'connector',
      description: c.description,
      canDisable: true,
      tools: [], // populated dynamically from connectorActions[c.id]
    }))
  }, [connectors])

  const allCategories = [...STATIC_TOOL_CATEGORIES, ...connectorCategories]

  // Filter by search
  const filteredCategories = useMemo(() => {
    if (!search.trim()) return allCategories
    const q = search.toLowerCase()
    return allCategories
      .map((cat) => ({
        ...cat,
        tools: cat.tools.filter(
          (t) => t.name.toLowerCase().includes(q) || t.description.toLowerCase().includes(q)
        ),
      }))
      .filter((cat) => cat.tools.length > 0 || cat.label.toLowerCase().includes(q))
  }, [allCategories, search])

  // Count tools needing confirmation
  const totalConfirm = useMemo(() => {
    let n = 0
    for (const cat of STATIC_TOOL_CATEGORIES) {
      for (const t of cat.tools) {
        const perm = toolPermissions[t.id] ?? t.defaultPermission
        if (perm === 'confirm' && !disabledTools.includes(t.id)) n++
      }
    }
    return n
  }, [toolPermissions, disabledTools])

  return (
    <div className='space-y-5'>
      {/* Header */}
      <div>
        <h3 className='text-base font-semibold text-white'>Tool Permissions</h3>
        <p className='mt-1 text-sm text-zinc-400'>
          Control which tools the agent can use and whether it must ask before using them.
          Tools set to <span className='text-amber-300 font-medium'>Ask for confirmation</span> will pause the agent and send you an approval card.
        </p>
      </div>

      {/* Confirmation summary pill */}
      {totalConfirm > 0 && (
        <div className='flex items-center gap-2 rounded-xl border border-amber-500/30 bg-amber-500/5 px-4 py-2.5'>
          <span className='text-amber-300 text-lg'>⚠️</span>
          <p className='text-xs text-amber-200'>
            <span className='font-semibold'>{totalConfirm} tool{totalConfirm > 1 ? 's' : ''}</span> require your confirmation before the agent can use them.
            An approval card will appear in Chat or your connected messaging channel.
          </p>
        </div>
      )}

      {/* Search */}
      <div className='relative'>
        <svg className='absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-zinc-500' fill='none' viewBox='0 0 24 24' stroke='currentColor' strokeWidth={2}>
          <path strokeLinecap='round' strokeLinejoin='round' d='m21 21-4.35-4.35M17 11A6 6 0 1 1 5 11a6 6 0 0 1 12 0Z' />
        </svg>
        <input
          type='text'
          placeholder='Search tools…'
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className='w-full rounded-xl border border-[#2a2a2a] bg-[#1a1a1a] py-2 pl-9 pr-3 text-sm text-zinc-200 placeholder:text-zinc-600 outline-none focus:border-blue-500/60'
        />
      </div>

      {/* Loading state for connectors */}
      {loadingConnectors && (
        <div className='flex items-center gap-2 text-xs text-zinc-500'>
          <div className='h-3 w-3 animate-spin rounded-full border border-zinc-600 border-t-zinc-300' />
          Loading connected apps…
        </div>
      )}

      {/* Categories */}
      <div className='space-y-3'>
        {filteredCategories.map((cat) => {
          const cId = cat.id.startsWith('connector-') ? cat.id.replace('connector-', '') : null
          return (
            <CategorySection
              key={cat.id}
              category={cat}
              toolPermissions={toolPermissions}
              disabledTools={disabledTools}
              onToolToggle={handleToolToggle}
              onPermissionChange={handlePermissionChange}
              connectorActions={cId ? connectorActions[cId] : undefined}
            />
          )
        })}
      </div>

      {/* Empty search result */}
      {filteredCategories.length === 0 && (
        <div className='rounded-xl border border-[#2a2a2a] bg-[#111] p-8 text-center text-sm text-zinc-500'>
          No tools match "{search}"
        </div>
      )}

      {/* Footer: reset */}
      <div className='flex justify-end'>
        <button
          type='button'
          onClick={() => onPatch({ toolPermissions: {}, disabledTools: [] })}
          className='rounded-xl border border-[#2a2a2a] px-4 py-2 text-xs text-zinc-400 hover:border-zinc-600 hover:text-zinc-200 transition-colors'
        >
          Reset all to defaults
        </button>
      </div>
    </div>
  )
}
