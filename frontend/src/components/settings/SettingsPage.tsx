import { useEffect, useState } from 'react'
import { Icons } from '../icons'
import { useSettingsContext } from '../../context/useSettingsContext'
import type { AppSettings } from '../../hooks/useSettings'
import type { SteeringMode } from '../../hooks/useWebSocket'
import { AgentTab } from './AgentTab'
import { APIKeysTab } from './APIKeysTab'
import { ConnectionsTab } from './ConnectionsTab'
import { ProfileTab } from './ProfileTab'
import { SupportTab } from './SupportTab'
import { UsageTab } from './UsageTab'
import { WorkflowsTab } from './WorkflowsTab'
import { CreditsTab } from './CreditsTab'
import { InvoiceTab } from './InvoiceTab'
import { MemoryTab } from './MemoryTab'
import { ObservabilityTab } from './ObservabilityTab'
import { AdminPanel } from '../admin/AdminPanel'

type SettingsPageProps = {
  onBack: () => void
  onRunWorkflow: (instruction: string, mode?: SteeringMode) => void
  initialTab?: SettingsTab
  isAdmin?: boolean
  onTabChange?: (tab: SettingsTab) => void
}

const TABS = ['Profile', 'Agent Configuration', 'API Keys', 'Usage', 'Credits', 'Invoices', 'Connections', 'Workflows', 'Memory', 'Observability', 'Support', 'Admin'] as const
export type SettingsTab = (typeof TABS)[number]
const TAB_KEY = 'aegis.settings.activeTab'

export function SettingsPage({ onBack, onRunWorkflow, initialTab, isAdmin = false, onTabChange }: SettingsPageProps) {
  const { settings, patchSettings } = useSettingsContext()

  const [activeTab, setActiveTab] = useState<SettingsTab>(() => {
    if (initialTab && TABS.includes(initialTab)) return initialTab
    const persisted = localStorage.getItem(TAB_KEY) as SettingsTab | null
    return persisted && TABS.includes(persisted) ? persisted : 'Profile'
  })

  // Mobile sidebar: visible by default, collapses on tab select
  const [sidebarOpen, setSidebarOpen] = useState(true)

  useEffect(() => {
    localStorage.setItem(TAB_KEY, activeTab)
  }, [activeTab])

  // If initialTab changes externally, switch to it
  useEffect(() => {
    if (initialTab && TABS.includes(initialTab)) {
      setActiveTab(initialTab)
      setSidebarOpen(false) // auto-collapse on mobile when navigating to a tab
    }
  }, [initialTab])

  const onPatch = (next: Partial<AppSettings>) => patchSettings(next)

  const selectTab = (tab: SettingsTab) => {
    setActiveTab(tab)
    onTabChange?.(tab)
    setSidebarOpen(false) // collapse sidebar on mobile after selecting
  }

  return (
    <section className='flex h-full w-full min-w-0 flex-col overflow-hidden rounded-2xl border border-[#2a2a2a] bg-[#1a1a1a] md:flex-row'>
      {/* ── Mobile top bar (visible < md) ── */}
      <div className='flex items-center justify-between border-b border-[#2a2a2a] px-3 py-2 md:hidden'>
        <button type='button' onClick={sidebarOpen ? onBack : () => setSidebarOpen(true)} className='inline-flex items-center gap-1 text-xs text-blue-300'>
          {Icons.back({ className: 'h-3.5 w-3.5' })}
          <span>{sidebarOpen ? 'Dashboard' : 'Settings'}</span>
        </button>
        <span className='text-xs font-semibold text-zinc-200'>{sidebarOpen ? 'Settings' : activeTab}</span>
        <button
          type='button'
          onClick={() => setSidebarOpen((o) => !o)}
          className='rounded border border-[#2a2a2a] p-1.5'
          aria-label='Toggle settings menu'
        >
          {sidebarOpen
            ? Icons.close?.({ className: 'h-4 w-4 text-zinc-400' }) ?? <span className='text-xs text-zinc-400'>✕</span>
            : Icons.menu?.({ className: 'h-4 w-4 text-zinc-400' }) ?? <span className='text-xs text-zinc-400'>☰</span>}
        </button>
      </div>

      {/* ── Sidebar nav ── */}
      <nav
        className={`${
          sidebarOpen ? 'block' : 'hidden'
        } w-full shrink-0 border-b border-[#2a2a2a] p-3 md:block md:w-56 lg:w-64 md:border-b-0 md:border-r`}
      >
        <button
          type='button'
          onClick={onBack}
          className='mb-4 hidden items-center gap-1 text-xs text-blue-300 md:inline-flex'
        >
          {Icons.back({ className: 'h-3.5 w-3.5' })}
          <span>Back to Dashboard</span>
        </button>
        <h2 className='mb-2 text-sm font-semibold'>Settings</h2>
        <div className='space-y-1'>
          {TABS.filter((tab) => tab !== 'Admin' || isAdmin).map((tab) => (
            <button
              key={tab}
              type='button'
              onClick={() => selectTab(tab)}
              className={`w-full rounded px-2 py-2 text-left text-sm ${
                activeTab === tab ? 'bg-blue-600 text-white' : 'text-zinc-300 hover:bg-zinc-800'
              } ${tab === 'Admin' ? 'mt-2 border-t border-[#2a2a2a] pt-3 text-red-400 hover:bg-red-500/10' : ''}`}
            >
              {tab === 'Admin' ? (
                <span className='flex items-center gap-1.5'>
                  <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2' strokeLinecap='round' strokeLinejoin='round' className='h-3.5 w-3.5'>
                    <path d='M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z'/>
                    <circle cx='12' cy='12' r='3'/>
                  </svg>
                  Admin
                </span>
              ) : tab}
            </button>
          ))}
        </div>
      </nav>

      {/* ── Content area ── */}
      <div className={`${sidebarOpen ? 'hidden md:block' : 'block'} min-h-0 min-w-0 flex-1 overflow-x-hidden overflow-y-auto p-3 sm:p-4`}>
        {activeTab === 'Profile' && <ProfileTab settings={settings} onPatch={onPatch} />}
        {activeTab === 'Agent Configuration' && <AgentTab settings={settings} onPatch={onPatch} />}
        {activeTab === 'API Keys' && <APIKeysTab />}
        {activeTab === 'Usage' && <UsageTab />}
        {activeTab === 'Credits' && <CreditsTab />}
        {activeTab === 'Invoices' && <InvoiceTab />}
        {activeTab === 'Connections' && (
          <ConnectionsTab
            integrations={settings.integrations}
            onChange={(integrations) => onPatch({ integrations })}
            isAdmin={isAdmin}
          />
        )}
        {activeTab === 'Workflows' && (
          <WorkflowsTab
            workflows={settings.workflowTemplates}
            onChange={(workflowTemplates) => onPatch({ workflowTemplates })}
            onRun={(instruction) => onRunWorkflow(instruction, 'steer')}
          />
        )}
        {activeTab === 'Memory' && <MemoryTab />}
        {activeTab === 'Observability' && <ObservabilityTab />}
        {activeTab === 'Support' && <SupportTab />}
        {activeTab === 'Admin' && isAdmin && <AdminPanel />}
      </div>
    </section>
  )
}
