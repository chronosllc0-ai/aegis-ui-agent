import type { AppSettings } from '../../hooks/useSettings'

const PRESETS: Record<string, string> = {
  Professional: 'Respond clearly and professionally with concise rationale.',
  Casual: 'Use friendly and conversational language with practical guidance.',
  Technical: 'Prioritize precise technical details and implementation tradeoffs.',
  Creative: 'Offer imaginative solutions and exploratory suggestions.',
}

const MODEL_DESCRIPTIONS: Record<string, string> = {
  'gemini-2.5-pro': 'Best for quality and complex reasoning tasks.',
  'gemini-2.5-flash': 'Fast responses and lower latency tool usage.',
}

type AgentTabProps = {
  settings: AppSettings
  onPatch: (next: Partial<AppSettings>) => void
}

export function AgentTab({ settings, onPatch }: AgentTabProps) {
  return (
    <div className='space-y-6'>
      <section className='space-y-3'>
        <h3 className='text-sm font-semibold'>Personality</h3>
        <textarea
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
        <input type='range' min={0} max={1} step={0.1} value={settings.temperature} onChange={(event) => onPatch({ temperature: Number(event.target.value) })} className='w-full' />
      </section>

      <section className='space-y-2'>
        <h3 className='text-sm font-semibold'>Model</h3>
        <select value={settings.model} onChange={(event) => onPatch({ model: event.target.value })} className='w-full rounded border border-[#2a2a2a] bg-[#111] px-3 py-2'>
          {Object.keys(MODEL_DESCRIPTIONS).map((model) => (
            <option key={model} value={model}>{model}</option>
          ))}
        </select>
        <p className='text-xs text-zinc-400'>{MODEL_DESCRIPTIONS[settings.model]}</p>
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
