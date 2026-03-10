import { useEffect, useState } from 'react'
import { useSettingsContext } from '../../context/SettingsContext'
import type { AppSettings } from '../../hooks/useSettings'
import type { SteeringMode } from '../../hooks/useWebSocket'
import { AgentTab } from './AgentTab'
import { IntegrationsTab } from './IntegrationsTab'
import { ProfileTab } from './ProfileTab'
import { WorkflowsTab } from './WorkflowsTab'

type SettingsPageProps = {
  onBack: () => void
  onRunWorkflow: (instruction: string, mode?: SteeringMode) => void
}

const TABS = ['Profile', 'Agent Configuration', 'Integrations', 'Workflows'] as const
const TAB_KEY = 'aegis.settings.activeTab'

function readInitialTab(): (typeof TABS)[number] {
  const persisted = localStorage.getItem(TAB_KEY) as (typeof TABS)[number] | null
  if (persisted && TABS.includes(persisted)) return persisted
  return 'Profile'
}

export function SettingsPage({ onBack, onRunWorkflow }: SettingsPageProps) {
  const { settings, patchSettings } = useSettingsContext()
  const [activeTab, setActiveTab] = useState<(typeof TABS)[number]>(readInitialTab)

  useEffect(() => {
    localStorage.setItem(TAB_KEY, activeTab)
  }, [activeTab])

  const onPatch = (next: Partial<AppSettings>) => patchSettings(next)

  return (
    <section className='h-full overflow-hidden rounded-2xl border border-[#2a2a2a] bg-[#161616]'>
      <header className='flex items-center justify-between border-b border-[#2a2a2a] px-5 py-3'>
        <div>
          <h2 className='text-lg font-semibold'>Settings</h2>
          <p className='text-xs text-zinc-500'>Control profile, model behavior, integrations, and workflow templates.</p>
        </div>
        <button type='button' onClick={onBack} className='rounded-md border border-[#2a2a2a] px-3 py-1.5 text-xs text-blue-300'>← Back to Dashboard</button>
      </header>

      <div className='grid h-[calc(100%-73px)] grid-cols-[230px_1fr]'>
        <nav className='border-r border-[#2a2a2a] bg-[#121212] p-3'>
          <div className='space-y-1'>
            {TABS.map((tab) => (
              <button key={tab} type='button' onClick={() => setActiveTab(tab)} className={`w-full rounded-xl px-3 py-2 text-left text-sm ${activeTab === tab ? 'bg-blue-600 text-white' : 'text-zinc-300 hover:bg-zinc-800'}`}>
                {tab}
              </button>
            ))}
          </div>
        </nav>

        <div className='overflow-y-auto p-6'>
          {activeTab === 'Profile' && <ProfileTab settings={settings} onPatch={onPatch} />}
          {activeTab === 'Agent Configuration' && <AgentTab settings={settings} onPatch={onPatch} />}
          {activeTab === 'Integrations' && <IntegrationsTab integrations={settings.integrations} onChange={(integrations) => onPatch({ integrations })} />}
          {activeTab === 'Workflows' && <WorkflowsTab workflows={settings.workflowTemplates} onChange={(workflowTemplates) => onPatch({ workflowTemplates })} onRun={(instruction) => onRunWorkflow(instruction, 'steer')} />}
        </div>
      </div>
    </section>
  )
}
