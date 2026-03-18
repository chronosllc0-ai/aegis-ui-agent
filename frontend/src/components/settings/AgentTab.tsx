import type { AppSettings } from '../../hooks/useSettings'
import { PROVIDERS, providerById, providerForModel, modelInfo } from '../../lib/models'

const PRESETS: Record<string, string> = {
  Professional: 'Respond clearly and professionally with concise rationale.',
  Casual: 'Use friendly and conversational language with practical guidance.',
  Technical: 'Prioritize precise technical details and implementation tradeoffs.',
  Creative: 'Offer imaginative solutions and exploratory suggestions.',
}

type AgentTabProps = {
  settings: AppSettings
  onPatch: (next: Partial<AppSettings>) => void
}

export function AgentTab({ settings, onPatch }: AgentTabProps) {
  const currentProvider = providerById(settings.provider) ?? providerForModel(settings.model) ?? PROVIDERS[0]
  const currentModel = modelInfo(settings.model)

  return (
    <div className='space-y-6'>
      <section className='space-y-3'>
        <h3 className='text-sm font-semibold'>Personality</h3>
        <label htmlFor='agent-system-instruction' className='text-xs font-medium text-zinc-400'>
          System instruction
        </label>
        <textarea
          id='agent-system-instruction'
          value={settings.systemInstruction}
          onChange={(event) => onPatch({ systemInstruction: event.target.value })}
          className='h-28 w-full rounded border border-[#2a2a2a] bg-[#111] p-3 text-sm'
        />
        <div className='flex gap-2'>
          {Object.entries(PRESETS).map(([name, prompt]) => (
            <button key={name} type='button' onClick={() => onPatch({ personalityPreset: name, systemInstruction: prompt })} className='rounded border border-[#2a2a2a] px-2 py-1 text-xs'>
              {name}
            </button>
          ))}
        </div>
        <label htmlFor='agent-temperature' className='text-xs font-medium text-zinc-400'>
          Temperature
        </label>
        <input
          id='agent-temperature'
          type='range'
          min={0}
          max={1}
          step={0.1}
          value={settings.temperature}
          onChange={(event) => onPatch({ temperature: Number(event.target.value) })}
          className='w-full'
        />
      </section>

      <section className='space-y-3'>
        <h3 className='text-sm font-semibold'>Provider & Model</h3>

        <label htmlFor='agent-provider' className='text-xs font-medium text-zinc-400'>
          Provider
        </label>
        <select
          id='agent-provider'
          value={currentProvider.id}
          onChange={(event) => {
            const provider = providerById(event.target.value)
            if (provider) onPatch({ provider: provider.id, model: provider.models[0].id })
          }}
          className='w-full rounded border border-[#2a2a2a] bg-[#111] px-3 py-2 text-zinc-100'
        >
          {PROVIDERS.map((p) => (
            <option key={p.id} value={p.id} className='bg-[#111] text-zinc-100'>
              {p.displayName}
            </option>
          ))}
        </select>

        <label htmlFor='agent-model' className='text-xs font-medium text-zinc-400'>
          Model
        </label>
        <select
          id='agent-model'
          aria-describedby='agent-model-description'
          value={settings.model}
          onChange={(event) => onPatch({ model: event.target.value })}
          className='w-full rounded border border-[#2a2a2a] bg-[#111] px-3 py-2 text-zinc-100'
        >
          {currentProvider.models.map((m) => (
            <option key={m.id} value={m.id} className='bg-[#111] text-zinc-100'>
              {m.label}
            </option>
          ))}
        </select>
        <p id='agent-model-description' className='text-xs text-zinc-400'>
          {currentModel?.description ?? 'Select a model for this session.'}
        </p>
      </section>

      <section className='space-y-2'>
        <h3 className='text-sm font-semibold'>Behavior</h3>
        <Toggle label='Auto-screenshot' checked={settings.autoScreenshot} onToggle={(value) => onPatch({ autoScreenshot: value })} />
        <Toggle label='Verbose logging' checked={settings.verboseLogging} onToggle={(value) => onPatch({ verboseLogging: value })} />
        <Toggle label='Confirm destructive actions' checked={settings.confirmDestructiveActions} onToggle={(value) => onPatch({ confirmDestructiveActions: value })} />
      </section>
    </div>
  )
}

function Toggle({ label, checked, onToggle }: { label: string; checked: boolean; onToggle: (value: boolean) => void }) {
  return (
    <button type='button' onClick={() => onToggle(!checked)} className='flex w-full items-center justify-between rounded border border-[#2a2a2a] px-3 py-2 text-sm'>
      <span>{label}</span>
      <span className={checked ? 'text-emerald-300' : 'text-zinc-500'}>{checked ? 'On' : 'Off'}</span>
    </button>
  )
}
