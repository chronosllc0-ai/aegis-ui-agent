import { DEFAULT_SYSTEM_INSTRUCTION, type AppSettings } from '../../hooks/useSettings'
import { PROVIDERS, providerById, providerForModel, modelInfo, reasoningModesForModel } from '../../lib/models'
import { ToolsTab } from './ToolsTab'

const PRESETS: Record<string, string> = {
  Professional: 'Respond clearly and professionally with concise rationale.',
  Casual: 'Use friendly and conversational language with practical guidance.',
  Technical: 'Prioritize precise technical details and implementation tradeoffs.',
  Creative: 'Offer imaginative solutions and exploratory suggestions.',
}

function presetInstruction(styleInstruction: string): string {
  return `${DEFAULT_SYSTEM_INSTRUCTION} ${styleInstruction}`
}

type AgentTabProps = {
  settings: AppSettings
  onPatch: (next: Partial<AppSettings>) => void
}

export function AgentTab({ settings, onPatch }: AgentTabProps) {
  const currentProvider = providerById(settings.provider) ?? providerForModel(settings.model) ?? PROVIDERS[0]
  const currentModel = modelInfo(settings.model)
  const supportsReasoning = Boolean(currentModel?.reasoning)
  const reasoningModes = reasoningModesForModel(settings.model)

  return (
    <div className='space-y-6'>
      <section className='space-y-3'>
        <h3 className='text-sm font-semibold'>Personality</h3>
        <label htmlFor='agent-system-instruction' className='text-xs font-medium text-zinc-400'>
          Runtime instructions
        </label>
        <p className='text-xs text-zinc-500'>
          These instructions are added to your session and guide how Aegis responds to you. Global
          operator instructions set by the platform admin always apply and take precedence.
        </p>
        <textarea
          id='agent-system-instruction'
          value={settings.systemInstruction}
          onChange={(event) => onPatch({ systemInstruction: event.target.value })}
          className='h-28 w-full rounded border border-[#2a2a2a] bg-[#111] p-3 text-sm'
        />
        <div className='flex gap-2'>
          {Object.entries(PRESETS).map(([name, prompt]) => (
            <button key={name} type='button' onClick={() => onPatch({ personalityPreset: name, systemInstruction: presetInstruction(prompt) })} className='rounded border border-[#2a2a2a] px-2 py-1 text-xs'>
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

        {settings.provider === 'chronos' && (
          <div className='inline-flex items-center gap-1.5 rounded-full border border-violet-500/40 bg-violet-500/10 px-3 py-1 text-xs font-medium text-violet-300'>
            <span className='h-1.5 w-1.5 rounded-full bg-violet-400' />
            Using Chronos Gateway · Credits deducted per request
          </div>
        )}

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

        {supportsReasoning && (
          <div className='rounded-xl border border-[#2a2a2a] bg-[#121212] p-3'>
            <div className='flex items-center justify-between gap-3'>
              <div>
                <p className='text-xs font-semibold text-zinc-200'>Enable reasoning</p>
                <p className='text-[11px] text-zinc-500'>Use model thinking for deeper multi-step planning.</p>
              </div>
              <button
                type='button'
                onClick={() => onPatch({ enableReasoning: !settings.enableReasoning })}
                className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                  settings.enableReasoning
                    ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300'
                    : 'border-[#2a2a2a] bg-[#181818] text-zinc-500'
                }`}
              >
                {settings.enableReasoning ? 'On' : 'Off'}
              </button>
            </div>

            {settings.enableReasoning && reasoningModes.length > 0 && (
              <div className='mt-3'>
                <p className='mb-1 text-[11px] font-medium text-zinc-400'>Reasoning control</p>
                <div className='flex flex-wrap gap-1.5'>
                  {reasoningModes.map((mode) => (
                    <button
                      key={mode}
                      type='button'
                      onClick={() => onPatch({ reasoningEffort: mode })}
                      className={`rounded-lg px-2.5 py-1 text-[11px] font-medium capitalize transition-colors ${
                        settings.reasoningEffort === mode
                          ? 'bg-violet-600 text-white'
                          : 'bg-[#1a1a1a] text-zinc-400 hover:text-zinc-200'
                      }`}
                    >
                      {mode}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </section>

      <section className='space-y-2'>
        <h3 className='text-sm font-semibold'>Behavior</h3>
        <Toggle label='Auto-screenshot' checked={settings.autoScreenshot} onToggle={(value) => onPatch({ autoScreenshot: value })} />
        <Toggle label='Verbose logging' checked={settings.verboseLogging} onToggle={(value) => onPatch({ verboseLogging: value })} />
        <Toggle label='Confirm destructive actions' checked={settings.confirmDestructiveActions} onToggle={(value) => onPatch({ confirmDestructiveActions: value })} />
        <Toggle label='Split chat/browser surfaces (beta)' checked={settings.separateExecutionSurfaces} onToggle={(value) => onPatch({ separateExecutionSurfaces: value })} />
        <Toggle label='Prompt to switch when browsing starts' checked={settings.promptToSwitchOnBrowse} onToggle={(value) => onPatch({ promptToSwitchOnBrowse: value })} />
        <Toggle label='Auto-return to chat on completion' checked={settings.autoReturnToChat} onToggle={(value) => onPatch({ autoReturnToChat: value })} />
      </section>

      <section className='space-y-3'>
        <div>
          <h3 className='text-sm font-semibold'>Tools & Permissions</h3>
          <p className='mt-1 text-xs text-zinc-500'>Control which tools Aegis can use and whether each requires your approval before running.</p>
        </div>
        <ToolsTab settings={settings} onPatch={onPatch} />
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
