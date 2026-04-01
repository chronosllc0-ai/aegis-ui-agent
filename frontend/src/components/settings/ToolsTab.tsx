/**
 * ToolsTab - unified tool permission centre.
 *
 * Tool visibility rules
 * ─────────────────────
 *  • System categories (Browser, Web Search, File System, Code Execution):
 *      Always present. ON by default. User can disable the whole category or
 *      individual tools - when disabled the tools are not sent to the agent.
 *
 *  • Built-in categories (Memory, Cron, Agent Interaction):
 *      Always present with no gating. Cannot be linked to a connection.
 *
 *  • Bot integration categories (Telegram, Slack Bot, Discord Bot, GitHub Bot):
 *      LOCKED behind their integration. Tools only appear once the matching
 *      integration has been saved and connected in the Connections tab.
 *      While locked, a banner is shown directing the user to connect first.
 *
 *  • OAuth connector categories (Google, Notion, Linear…):
 *      Injected dynamically from the backend - only active connectors appear.
 *      Already gated: the backend /api/connectors endpoint only returns
 *      connectors that are connected & active.
 */

import { useState, useMemo, useEffect, type ReactElement } from 'react'
import type { AppSettings, ToolPermission } from '../../hooks/useSettings'
import { GITHUB_PAT_INTEGRATION_ID, type IntegrationConfig } from '../../lib/mcp'
import { BrandIcon } from '../icons'
import { apiUrl } from '../../lib/api'

// ── Tool catalogue ────────────────────────────────────────────────────────────

export type ToolCategory = {
  id: string
  label: string
  /** Either a key from CATEGORY_ICONS or an https:// URL for OAuth connectors */
  icon: string
  description: string
  tools: ToolDef[]
  canDisable?: boolean
  /**
   * If set, this category is gated behind the integration with this id.
   * Tools are hidden until that integration is `status === 'connected'`.
   */
  requiresIntegrationId?: string
}

export type ToolDef = {
  id: string
  name: string
  description: string
  risk: 'low' | 'medium' | 'high'
  defaultPermission: ToolPermission
}

// ── System / built-in tool definitions ───────────────────────────────────────

const BROWSER_TOOLS: ToolDef[] = [
  { id: 'screenshot',   name: 'Screenshot',      description: 'Capture the current browser viewport',  risk: 'low',    defaultPermission: 'auto' },
  { id: 'go_to_url',    name: 'Navigate',         description: 'Navigate to a URL',                     risk: 'low',    defaultPermission: 'auto' },
  { id: 'click',        name: 'Click',            description: 'Click an element on the page',           risk: 'low',    defaultPermission: 'auto' },
  { id: 'type_text',    name: 'Type Text',        description: 'Type text into a focused element',       risk: 'low',    defaultPermission: 'auto' },
  { id: 'scroll',       name: 'Scroll',           description: 'Scroll the page',                        risk: 'low',    defaultPermission: 'auto' },
  { id: 'wait',         name: 'Wait',             description: 'Pause execution briefly',                risk: 'low',    defaultPermission: 'auto' },
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
  { id: 'telegram_get_messages',  name: 'Read Messages',  description: 'Read Telegram messages',         risk: 'low',    defaultPermission: 'auto' },
  { id: 'telegram_send_message',  name: 'Send Message',   description: 'Send a Telegram message',        risk: 'medium', defaultPermission: 'confirm' },
  { id: 'telegram_send_image',    name: 'Send Image',     description: 'Send an image via Telegram',     risk: 'medium', defaultPermission: 'confirm' },
  { id: 'telegram_list_chats',    name: 'List Chats',     description: 'List Telegram chats/channels',   risk: 'low',    defaultPermission: 'auto' },
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
  { id: 'github_list_repos',           name: 'List Repos',          description: 'List repositories',                                  risk: 'low',    defaultPermission: 'auto' },
  { id: 'github_get_issues',           name: 'Get Issues',          description: 'Fetch issues from a repo',                           risk: 'low',    defaultPermission: 'auto' },
  { id: 'github_create_issue',         name: 'Create Issue',        description: 'Open a new GitHub issue',                            risk: 'medium', defaultPermission: 'confirm' },
  { id: 'github_get_pull_requests',    name: 'Get PRs',             description: 'Fetch pull requests',                                risk: 'low',    defaultPermission: 'auto' },
  { id: 'github_create_comment',       name: 'Create Comment',      description: 'Post a comment on a PR or issue',                    risk: 'medium', defaultPermission: 'confirm' },
  { id: 'github_get_file',             name: 'Get File',            description: 'Read a file directly from a repo',                   risk: 'low',    defaultPermission: 'auto' },
  { id: 'github_clone_repo',           name: 'Clone Repo',          description: 'Clone a repo into the current Aegis session',        risk: 'low',    defaultPermission: 'auto' },
  { id: 'github_create_branch',        name: 'Create Branch',       description: 'Create or reset a working branch locally',           risk: 'low',    defaultPermission: 'auto' },
  { id: 'github_repo_status',          name: 'Repo Status',         description: 'Inspect local git status for a cloned repo',         risk: 'low',    defaultPermission: 'auto' },
  { id: 'github_repo_diff',            name: 'Repo Diff',           description: 'Read local git diffs for a cloned repo',             risk: 'low',    defaultPermission: 'auto' },
  { id: 'github_commit_changes',       name: 'Commit Changes',      description: 'Stage and commit local repo changes',                risk: 'medium', defaultPermission: 'confirm' },
  { id: 'github_push_branch',          name: 'Push Branch',         description: 'Push the current branch to GitHub',                  risk: 'high',   defaultPermission: 'confirm' },
  { id: 'github_create_pull_request',  name: 'Create Pull Request', description: 'Open a mergeable pull request from the local branch', risk: 'high',   defaultPermission: 'confirm' },
]

const MEMORY_TOOLS: ToolDef[] = [
  { id: 'memory_search', name: 'Memory Search',  description: 'Semantic search through stored memories',           risk: 'low',    defaultPermission: 'auto' },
  { id: 'memory_write',  name: 'Memory Write',   description: 'Store a new memory entry',                         risk: 'medium', defaultPermission: 'auto' },
  { id: 'memory_read',   name: 'Memory Read',    description: 'Read a specific memory entry by ID',               risk: 'low',    defaultPermission: 'auto' },
  { id: 'memory_patch',  name: 'Memory Patch',   description: 'Update an existing memory entry',                  risk: 'medium', defaultPermission: 'auto' },
]

const AGENT_INTERACTION_TOOLS: ToolDef[] = [
  { id: 'ask_user_input',  name: 'Ask User Input',  description: 'Pause and ask the user a question mid-task',        risk: 'low',    defaultPermission: 'auto' },
  { id: 'summarize_task',  name: 'Summarize Task',  description: 'Generate a structured summary of completed work',   risk: 'low',    defaultPermission: 'auto' },
  { id: 'confirm_plan',    name: 'Confirm Plan',    description: 'Present a plan for user approval before executing',  risk: 'low',    defaultPermission: 'auto' },
]

const CRON_TOOLS: ToolDef[] = [
  { id: 'cron_write',  name: 'Create Automation', description: 'Create a new scheduled automation task',            risk: 'medium', defaultPermission: 'confirm' },
  { id: 'cron_patch',  name: 'Edit Automation',   description: 'Modify an existing scheduled automation',           risk: 'medium', defaultPermission: 'confirm' },
  { id: 'cron_delete', name: 'Delete Automation', description: 'Permanently delete a scheduled automation',         risk: 'high',   defaultPermission: 'confirm' },
]

// ── Category icon SVGs ────────────────────────────────────────────────────────

const CATEGORY_ICONS: Record<string, ReactElement> = {
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
  // Bot integrations - real brand icons via BrandIcon
  telegram:    <BrandIcon id='telegram'  className='h-5 w-5' />,
  'slack-bot': <BrandIcon id='slack'     className='h-5 w-5' />,
  discord:     <BrandIcon id='discord'   className='h-5 w-5' />,
  'github-bot':<BrandIcon id='github'    className='h-5 w-5' />,
  connector: (
    <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2' strokeLinecap='round' strokeLinejoin='round' className='h-5 w-5 text-zinc-300'>
      <path d='M12 22v-5'/><path d='M9 8V2'/><path d='M15 8V2'/>
      <path d='M18 8H6a2 2 0 0 0-2 2v2a7 7 0 0 0 7 7h2a7 7 0 0 0 7-7v-2a2 2 0 0 0-2-2Z'/>
    </svg>
  ),
}

const FallbackCategoryIcon = () => (
  <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2' strokeLinecap='round' strokeLinejoin='round' className='h-5 w-5 text-zinc-300'>
    <path d='M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71'/>
    <path d='M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71'/>
  </svg>
)

// ── Static category list ──────────────────────────────────────────────────────

const STATIC_TOOL_CATEGORIES: ToolCategory[] = [
  // ── System tools - always present, on by default ─────────────────────────
  {
    id: 'browser',
    label: 'Browser Control',
    icon: 'browser',
    description: 'Core browser automation - navigate, click, type, screenshot. On by default.',
    canDisable: true,
    tools: BROWSER_TOOLS,
  },
  {
    id: 'web-search',
    label: 'Web Search',
    icon: 'web-search',
    description: 'Search the internet and extract page content. On by default.',
    canDisable: true,
    tools: WEB_TOOLS,
  },
  {
    id: 'filesystem',
    label: 'File System',
    icon: 'filesystem',
    description: 'Read and write local files. On by default.',
    canDisable: true,
    tools: FILESYSTEM_TOOLS,
  },
  {
    id: 'code-exec',
    label: 'Code Execution',
    icon: 'code-exec',
    description: 'Run Python and JavaScript in a sandbox. On by default.',
    canDisable: true,
    tools: CODE_TOOLS,
  },
  // ── Built-in tools - always present, no gating ───────────────────────────
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
  // ── Bot integration tools - gated behind connected integration ────────────
  {
    id: 'telegram',
    label: 'Telegram Bot',
    icon: 'telegram',
    description: 'Send and receive messages via your Telegram bot.',
    canDisable: true,
    requiresIntegrationId: 'telegram',
    tools: TELEGRAM_TOOLS,
  },
  {
    id: 'slack-bot',
    label: 'Slack Bot',
    icon: 'slack-bot',
    description: 'Interact with Slack workspaces via your bot token.',
    canDisable: true,
    requiresIntegrationId: 'slack',
    tools: SLACK_BOT_TOOLS,
  },
  {
    id: 'discord',
    label: 'Discord Bot',
    icon: 'discord',
    description: 'Interact with Discord servers via your bot.',
    canDisable: true,
    requiresIntegrationId: 'discord',
    tools: DISCORD_TOOLS,
  },
  {
    id: 'github-bot',
    label: 'GitHub Bot',
    icon: 'github-bot',
    description: 'Manage repos, issues, and PRs via a personal access token.',
    canDisable: true,
    requiresIntegrationId: GITHUB_PAT_INTEGRATION_ID,
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
      <Toggle checked={enabled} onToggle={onToggle} />
      <div className='min-w-0 flex-1'>
        <div className='flex items-center gap-1.5 flex-wrap'>
          <span className='text-xs font-medium text-zinc-200'>{tool.name}</span>
          <RiskBadge risk={tool.risk} />
        </div>
        <p className='text-[10px] text-zinc-500 leading-snug mt-0.5'>{tool.description}</p>
      </div>
      {enabled && (
        <PermissionSelect value={permission} onChange={onPermissionChange} />
      )}
    </div>
  )
}

// ── Lock banner - shown when a bot integration isn't connected yet ─────────────

function IntegrationLockBanner({ label, integrationLabel }: { label: string; integrationLabel: string }) {
  return (
    <div className='border-t border-[#2a2a2a] px-4 py-5'>
      <div className='flex flex-col items-center gap-3 rounded-xl border border-dashed border-[#3a3a3a] bg-[#0d0d0d] px-4 py-6 text-center'>
        {/* lock icon */}
        <span className='flex h-9 w-9 items-center justify-center rounded-full border border-[#3a3a3a] bg-[#1a1a1a]'>
          <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2' strokeLinecap='round' strokeLinejoin='round' className='h-4 w-4 text-zinc-500'>
            <rect x='3' y='11' width='18' height='11' rx='2'/><path d='M7 11V7a5 5 0 0 1 10 0v4'/>
          </svg>
        </span>
        <div>
          <p className='text-xs font-medium text-zinc-300'>{label} tools are locked</p>
          <p className='mt-1 text-[11px] text-zinc-500 leading-snug max-w-[260px]'>
            Connect your <span className='text-zinc-300'>{integrationLabel}</span> integration in the{' '}
            <span className='text-blue-400'>Integrations</span> tab to unlock these tools.
          </p>
        </div>
      </div>
    </div>
  )
}

// ── Category section ──────────────────────────────────────────────────────────

type ConnectorAction = {
  id: string
  name: string
  description: string
  parameters: Record<string, string>
  category: string
}

function CategorySection({
  category,
  toolPermissions,
  disabledTools,
  onToolToggle,
  onPermissionChange,
  connectorActions,
  locked,
}: {
  category: ToolCategory
  toolPermissions: Record<string, ToolPermission>
  disabledTools: string[]
  onToolToggle: (toolId: string) => void
  onPermissionChange: (toolId: string, p: ToolPermission) => void
  connectorActions?: ConnectorAction[]
  locked?: boolean
}) {
  const [expanded, setExpanded] = useState(true)

  const allTools: ToolDef[] = useMemo(() => {
    const base = [...category.tools]
    if (connectorActions) {
      for (const a of connectorActions) {
        if (!base.find((t) => t.id === a.id)) {
          base.push({ id: a.id, name: a.name, description: a.description, risk: 'medium', defaultPermission: 'auto' })
        }
      }
    }
    return base
  }, [category.tools, connectorActions])

  const enabledCount = locked ? 0 : allTools.filter((t) => !disabledTools.includes(t.id)).length
  const confirmCount = locked ? 0 : allTools.filter((t) => {
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
          {category.icon.startsWith('http') ? (
            <img src={category.icon} alt={category.label} className='h-5 w-5 rounded object-contain'
              onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }} />
          ) : (
            CATEGORY_ICONS[category.icon] ?? <FallbackCategoryIcon />
          )}
        </span>
        <div className='min-w-0 flex-1'>
          <div className='flex items-center gap-2'>
            <span className='text-sm font-semibold text-zinc-100'>{category.label}</span>
            {locked ? (
              <span className='rounded border border-zinc-600/40 bg-zinc-700/20 px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wide text-zinc-500'>
                Not connected
              </span>
            ) : (
              <span className='text-[10px] text-zinc-500'>
                {enabledCount}/{allTools.length} active
                {confirmCount > 0 && ` · ${confirmCount} need confirmation`}
              </span>
            )}
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

      {/* Body - lock banner or tool rows */}
      {expanded && locked && (
        <IntegrationLockBanner label={category.label} integrationLabel={category.label.replace(' Bot', '').replace(' (Bot Token)', '')} />
      )}
      {expanded && !locked && (
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

// ── OAuth connector meta type ─────────────────────────────────────────────────

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

  // Build a lookup: integrationId → connected?
  const integrationConnected = useMemo(() => {
    const map: Record<string, boolean> = {}
    for (const integration of (settings.integrations ?? []) as IntegrationConfig[]) {
      map[integration.id] = integration.status === 'connected' && integration.enabled
    }
    return map
  }, [settings.integrations])

  const handleToolToggle = (toolId: string) => {
    const next = disabledTools.includes(toolId)
      ? disabledTools.filter((id) => id !== toolId)
      : [...disabledTools, toolId]
    onPatch({ disabledTools: next })
  }

  const handlePermissionChange = (toolId: string, perm: ToolPermission) => {
    onPatch({ toolPermissions: { ...toolPermissions, [toolId]: perm } })
  }

  // OAuth connector categories (only connected ones returned by backend)
  const connectorCategories: ToolCategory[] = useMemo(() => {
    return connectors.map((c) => ({
      id: `connector-${c.id}`,
      label: c.name,
      icon: c.icon || 'connector',
      description: c.description,
      canDisable: true,
      tools: [],
    }))
  }, [connectors])

  const allCategories = [...STATIC_TOOL_CATEGORIES, ...connectorCategories]

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

  const totalConfirm = useMemo(() => {
    let n = 0
    for (const cat of STATIC_TOOL_CATEGORIES) {
      if (cat.requiresIntegrationId && !integrationConnected[cat.requiresIntegrationId]) continue
      for (const t of cat.tools) {
        const perm = toolPermissions[t.id] ?? t.defaultPermission
        if (perm === 'confirm' && !disabledTools.includes(t.id)) n++
      }
    }
    return n
  }, [toolPermissions, disabledTools, integrationConnected])

  return (
    <div className='space-y-5'>
      {/* Header */}
      <div>
        <h3 className='text-base font-semibold text-white'>Tool Permissions</h3>
        <p className='mt-1 text-sm text-zinc-400'>
          Control which tools the agent can use and whether it must ask before using them.
          Tools set to <span className='text-amber-300 font-medium'>Ask for confirmation</span> will pause the agent and send you an approval card.
          Bot integration tools only appear once their credentials are connected.
        </p>
      </div>

      {/* Confirmation summary pill */}
      {totalConfirm > 0 && (
        <div className='flex items-center gap-2 rounded-xl border border-amber-500/30 bg-amber-500/5 px-4 py-2.5'>
          <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2' strokeLinecap='round' strokeLinejoin='round' className='h-4 w-4 shrink-0 text-amber-400'>
            <path d='M10.3 3.6 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.6a2 2 0 0 0-3.4 0Z'/><path d='M12 9v4M12 17h.01'/>
          </svg>
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

      {/* Loading state */}
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
          // A category is locked when it requires an integration that isn't connected yet
          const locked = Boolean(
            cat.requiresIntegrationId && !integrationConnected[cat.requiresIntegrationId]
          )
          return (
            <CategorySection
              key={cat.id}
              category={cat}
              toolPermissions={toolPermissions}
              disabledTools={disabledTools}
              onToolToggle={handleToolToggle}
              onPermissionChange={handlePermissionChange}
              connectorActions={cId ? connectorActions[cId] : undefined}
              locked={locked}
            />
          )
        })}
      </div>

      {filteredCategories.length === 0 && (
        <div className='rounded-xl border border-[#2a2a2a] bg-[#111] p-8 text-center text-sm text-zinc-500'>
          No tools match "{search}"
        </div>
      )}

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
