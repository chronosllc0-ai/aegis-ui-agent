import type { ReactNode } from 'react'
import { HeaderBar } from '../ui/DesignSystem'
import type { AppSettings } from '../../hooks/useSettings'
import type { SettingsTab } from './SettingsPage'
import { AgentTab } from './AgentTab'
import { APIKeysTab } from './APIKeysTab'
import { ConnectionsTab } from './ConnectionsTab'
import { CreditsTab } from './CreditsTab'
import { InvoiceTab } from './InvoiceTab'
import { MemoryTab } from './MemoryTab'
import { ObservabilityTab } from './ObservabilityTab'
import { SkillsTab } from './SkillsTab'
import { SupportTab } from './SupportTab'
import { AdminPanel } from '../admin/AdminPanel'

type StandaloneSettingsPageProps = {
  tab: SettingsTab
  settings: AppSettings
  onPatch: (next: Partial<AppSettings>) => void
  authRole?: string
  isAdmin?: boolean
}

type HeaderMeta = {
  title: string
  subtitle?: string
  right?: ReactNode
}

const HEADER_BY_TAB: Partial<Record<SettingsTab, HeaderMeta>> = {
  'Agent Configuration': {
    title: 'Agent Configuration',
    subtitle: 'Configure model behavior, reasoning, tools, and runtime defaults.',
  },
  'API Keys': {
    title: 'API Keys',
    subtitle: 'Manage your provider credentials and Bring-Your-Own-Key connections.',
  },
  Billing: {
    title: 'Billing',
    subtitle: 'View subscription, credits, and invoice history.',
  },
  Connections: {
    title: 'Connections',
    subtitle: 'Configure OAuth, MCP servers, and external tool integrations.',
  },
  Memory: {
    title: 'Memory',
    subtitle: 'Store reusable facts, preferences, and instructions for future tasks.',
  },
  Observability: {
    title: 'Observability',
    subtitle: 'Review runtime telemetry, task outcomes, and event-level diagnostics.',
  },
  Skills: {
    title: 'Skills',
    subtitle: 'Enable, review, and manage runtime skills available to your agent.',
  },
  Support: {
    title: 'Support',
    subtitle: 'Open and manage support conversations with the Aegis team.',
  },
  Admin: {
    title: 'Admin',
    subtitle: 'Manage users, platform controls, and operations from one workspace.',
  },
}

export function StandaloneSettingsPage({ tab, settings, onPatch, authRole, isAdmin = false }: StandaloneSettingsPageProps) {
  const headerMeta = HEADER_BY_TAB[tab]

  if (!headerMeta) return null

  return (
    <div className='h-full min-h-0 overflow-y-auto'>
      <div className='space-y-4 p-2 sm:p-3'>
        <HeaderBar
          left={(
            <div>
              <h2 className='text-base font-semibold text-white'>{headerMeta.title}</h2>
              {headerMeta.subtitle && <p className='text-xs text-zinc-400'>{headerMeta.subtitle}</p>}
            </div>
          )}
          right={headerMeta.right}
        />

        <div className='space-y-6'>
          {tab === 'Agent Configuration' && <AgentTab settings={settings} onPatch={onPatch} />}
          {tab === 'API Keys' && <APIKeysTab />}
          {tab === 'Billing' && (
            <div className='space-y-6'>
              <CreditsTab />
              <InvoiceTab />
            </div>
          )}
          {tab === 'Connections' && (
            <ConnectionsTab
              integrations={settings.integrations}
              onChange={(integrations) => onPatch({ integrations })}
              isAdmin={isAdmin}
            />
          )}
          {tab === 'Memory' && <MemoryTab />}
          {tab === 'Observability' && <ObservabilityTab />}
          {tab === 'Skills' && <SkillsTab role={authRole} />}
          {tab === 'Support' && <SupportTab />}
          {tab === 'Admin' && isAdmin && <AdminPanel />}
        </div>
      </div>
    </div>
  )
}
