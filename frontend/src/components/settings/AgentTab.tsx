import { useMemo } from 'react'
import type { AppSettings } from '../../hooks/useSettings'

const PRESETS: Record<string, string> = {
  Precise: 'Prioritize exactness, low-risk actions, and explicit confirmation before uncertain operations.',
  Fast: 'Optimize for speed and concise updates while still being safe with destructive actions.',
  Researcher: 'Use deeper analysis, compare options, and provide evidence-backed decisions.',
  Operator: 'Act as an execution copilot, narrate steps, and proactively continue when safe.',
}

const MODEL_DESCRIPTIONS: Record<string, string> = {
  'gemini-2.5-pro': 'Best for high-quality reasoning and complex multi-step planning.',
  'gemini-2.5-flash': 'Lower latency for quick interactions and frequent steering.',
}

type AgentTabProps = {
  settings: AppSettings
  onPatch: (next: Partial<AppSettings>) => void
}

export function AgentTab({ settings, onPatch }: AgentTabProps) {
  const temperatureLabel = useMemo(() => settings.temperature.toFixed(1), [settings.temperature])

  const restoreDefaults = () => {
    onPatch({
      personalityPreset: 'Operator',
      systemInstruction: PRESETS.Operator,
      temperature: 0.7,
      model: 'gemini-2.5-pro',
      autoScreenshot: true,
      verboseLogging: false,
      confirmDestructiveActions: true,
      narrateActions: true,
      allowAutonomousContinuation: false,
      requireExternalMessagingPermission: true,
    })
  }

  return (
    <div className='mx-auto max-w-4xl space-y-6'>
      <header className='flex items-center justify-between'>
        <div>
          <h3 className='text-lg font-semibold'>Agent Configuration</h3>
          <p className='text-sm text-zinc-400'>Tune model, personality, and operating behavior for your navigation sessions.</p>
        </div>
        <button type='button' onClick={restoreDefaults} className='rounded-md border border-[#2a2a2a] px-3 py-2 text-xs'>Restore defaults</button>
      </header>

      <section className='rounded-2xl border border-[#2a2a2a] bg-[#111] p-5'>
        <h4 className='mb-3 text-sm font-semibold'>Model & Temperature</h4>
        <div className='grid gap-4 md:grid-cols-2'>
          <label className='text-sm'>
            Model variant
            <select value={settings.model} onChange={(event) => onPatch({ model: event.target.value })} className='mt-1 w-full rounded-lg border border-[#2a2a2a] bg-[#0c0c0c] px-3 py-2'>
              {Object.keys(MODEL_DESCRIPTIONS).map((model) => <option key={model} value={model}>{model}</option>)}
            </select>
            <p className='mt-1 text-xs text-zinc-500'>{MODEL_DESCRIPTIONS[settings.model]}</p>
          </label>

          <div>
            <div className='flex items-center justify-between text-sm'>
              <span>Temperature</span>
              <span className='text-blue-300'>{temperatureLabel}</span>
            </div>
            <input type='range' min={0} max={1} step={0.1} value={settings.temperature} onChange={(event) => onPatch({ temperature: Number(event.target.value) })} className='mt-2 w-full' />
            <div className='mt-1 flex justify-between text-xs text-zinc-500'><span>Precise</span><span>Creative</span></div>
          </div>
        </div>
      </section>

      <section className='rounded-2xl border border-[#2a2a2a] bg-[#111] p-5'>
        <h4 className='mb-3 text-sm font-semibold'>Personality</h4>
        <div className='grid gap-2 sm:grid-cols-2 lg:grid-cols-4'>
          {Object.entries(PRESETS).map(([preset, prompt]) => (
            <button key={preset} type='button' onClick={() => onPatch({ personalityPreset: preset, systemInstruction: prompt })} className={`rounded-xl border px-3 py-2 text-left text-xs ${settings.personalityPreset === preset ? 'border-blue-500/60 bg-blue-500/10' : 'border-[#2a2a2a] hover:border-zinc-600'}`}>
              <p className='mb-1 text-sm font-medium'>{preset}</p>
              <p className='text-zinc-400'>{prompt.slice(0, 75)}…</p>
            </button>
          ))}
        </div>

        <label className='mt-4 block text-sm'>
          System instructions
          <textarea value={settings.systemInstruction} onChange={(event) => onPatch({ systemInstruction: event.target.value })} className='mt-1 h-28 w-full rounded-lg border border-[#2a2a2a] bg-[#0c0c0c] p-3 text-sm' />
          <p className='mt-1 text-xs text-zinc-500'>These instructions are sent at session start and shape agent behavior.</p>
        </label>
      </section>

      <section className='rounded-2xl border border-[#2a2a2a] bg-[#111] p-5'>
        <h4 className='mb-3 text-sm font-semibold'>Behavior</h4>
        <div className='grid gap-2 md:grid-cols-2'>
          <Toggle label='Auto-screenshot after every action' checked={settings.autoScreenshot} onToggle={(value) => onPatch({ autoScreenshot: value })} />
          <Toggle label='Verbose action logging' checked={settings.verboseLogging} onToggle={(value) => onPatch({ verboseLogging: value })} />
          <Toggle label='Confirm destructive actions' checked={settings.confirmDestructiveActions} onToggle={(value) => onPatch({ confirmDestructiveActions: value })} />
          <Toggle label='Narrate actions in real time' checked={settings.narrateActions} onToggle={(value) => onPatch({ narrateActions: value })} />
          <Toggle label='Allow autonomous continuation' checked={settings.allowAutonomousContinuation} onToggle={(value) => onPatch({ allowAutonomousContinuation: value })} />
          <Toggle label='Require permission for external messaging' checked={settings.requireExternalMessagingPermission} onToggle={(value) => onPatch({ requireExternalMessagingPermission: value })} />
        </div>
      </section>
    </div>
  )
}

function Toggle({ label, checked, onToggle }: { label: string; checked: boolean; onToggle: (value: boolean) => void }) {
  return (
    <button type='button' onClick={() => onToggle(!checked)} className='flex items-center justify-between rounded-lg border border-[#2a2a2a] px-3 py-2 text-sm hover:border-zinc-600'>
      <span>{label}</span>
      <span className={`text-xs ${checked ? 'text-emerald-300' : 'text-zinc-500'}`}>{checked ? 'On' : 'Off'}</span>
    </button>
  )
}
