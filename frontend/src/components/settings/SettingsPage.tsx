import { useEffect, useState } from 'react'
import { useSettingsContext } from '../../context/useSettingsContext'
import type { AppSettings } from '../../hooks/useSettings'
import type { SteeringMode } from '../../hooks/useWebSocket'
import { Icons } from '../icons'
import { AgentTab } from './AgentTab'
import { APIKeysTab } from './APIKeysTab'
import { IntegrationsTab } from './IntegrationsTab'
import { ProfileTab } from './ProfileTab'
import { WorkflowsTab } from './WorkflowsTab'

type SettingsPageProps = {
  onBack: () => void
  onRunWorkflow: (instruction: string, mode?: SteeringMode) => void
}

const TABS = ['Profile', 'Agent Configuration', 'API Keys', 'Integrations', 'Workflows'] as const
const TAB_KEY = 'aegis.settings.activeTab'

export function SettingsPage({ onBack, onRunWorkflow }: SettingsPageProps) {
  const { settings, patchSettings } = useSettingsContext()
  const [activeTab, setActiveTab] = useState<(typeof TABS)[number]>(() => {
    if (typeof window === 'undefined') return 'Profile'
    const persisted = window.localStorage.getItem(TAB_KEY) as (typeof TABS)[number] | null
    return persisted && TABS.includes(persisted) ? persisted : 'Profile'
  })

  useEffect(() => {
    localStorage.setItem(TAB_KEY, activeTab)
  }, [activeTab])

  const onPatch = (next: Partial<AppSettings>) => patchSettings(next)

  return (
    <section className='flex h-full rounded-2xl border border-[#2a2a2a] bg-[#1a1a1a]'>
      <nav className='w-64 border-r border-[#2a2a2a] p-3'>
        <button type='button' onClick={onBack} className='mb-4 inline-flex items-center gap-1 text-xs text-blue-300'>
          {Icons.back({ className: 'h-3.5 w-3.5' })}
          <span>Back to Dashboard</span>
        </button>
        <h2 className='mb-2 text-sm font-semibold'>Settings</h2>
        <div className='space-y-1'>
          {TABS.map((tab) => (
            <button key={tab} type='button' onClick={() => setActiveTab(tab)} className={`w-full rounded px-2 py-2 text-left text-sm ${activeTab === tab ? 'bg-blue-600 text-white' : 'text-zinc-300 hover:bg-zinc-800'}`}>
              {tab}
            </button>
          ))}
        </div>
      </nav>
      <div className='flex-1 overflow-y-auto p-4'>
        {activeTab === 'Profile' && <ProfileTab settings={settings} onPatch={onPatch} />}
        {activeTab === 'Agent Configuration' && <AgentTab settings={settings} onPatch={onPatch} />}
        {activeTab === 'API Keys' && <APIKeysTab />}
        {activeTab === 'Integrations' && <IntegrationsTab integrations={settings.integrations} onChange={(integrations) => onPatch({ integrations })} />}
        {activeTab === 'Workflows' && <WorkflowsTab workflows={settings.workflowTemplates} onChange={(workflowTemplates) => onPatch({ workflowTemplates })} onRun={(instruction) => onRunWorkflow(instruction, 'steer')} />}
      </div>
    </section>
  )
}
