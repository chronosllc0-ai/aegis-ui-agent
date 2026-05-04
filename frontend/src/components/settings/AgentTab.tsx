import { useState } from 'react'
import type { AppSettings, ReasoningEffort } from '../../hooks/useSettings'
import { THINKING_EFFORT_LABELS } from '../../hooks/useSettings'
import { clampReasoningEffort, modelInfoForProvider, PROVIDERS, providerById, providerForModel, supportedReasoningEffortsForModel } from '../../lib/models'
import { ToolsTab } from './ToolsTab'
import { WorkspaceFilesTab } from './WorkspaceFilesTab'

type AgentTabProps = {
  settings: AppSettings
  onPatch: (next: Partial<AppSettings>) => void
}

export function AgentTab({ settings, onPatch }: AgentTabProps) {
  const [activeSubtab, setActiveSubtab] = useState<'general' | 'workspace'>('general')
  const currentProvider = providerById(settings.provider) ?? providerForModel(settings.model) ?? PROVIDERS[0]
  const currentModel = modelInfoForProvider(currentProvider.id, settings.model)
  const availableReasoningEfforts = supportedReasoningEffortsForModel(currentProvider.id, settings.model)
  const supportsReasoning = Boolean(currentModel?.reasoning)
  const canConfigureReasoning = availableReasoningEfforts.some((effort) => effort !== 'none')
  const selectedReasoningEffort = settings.enableReasoning
    ? clampReasoningEffort(currentProvider.id, settings.model, settings.reasoningEffort)
    : 'none'

  return (
    <div className='space-y-6'>
      <div className='inline-flex rounded-lg border border-[#2a2a2a] bg-[#0f0f0f] p-1'>
        <button
          type='button'
          onClick={() => setActiveSubtab('general')}
          className={`rounded px-3 py-1.5 text-xs ${activeSubtab === 'general' ? 'bg-zinc-700 text-white' : 'text-zinc-400'}`}
        >
          General
        </button>
        <button
          type='button'
          onClick={() => setActiveSubtab('workspace')}
          className={`rounded px-3 py-1.5 text-xs ${activeSubtab === 'workspace' ? 'bg-zinc-700 text-white' : 'text-zinc-400'}`}
        >
          Workspace Files
        </button>
      </div>

      {activeSubtab === 'workspace' ? (
        <WorkspaceFilesTab
          editableUserFiles
          userFiles={settings.userWorkspaceFiles}
          onUserFilesChange={(userWorkspaceFiles) => onPatch({ userWorkspaceFiles })}
        />
      ) : (
        <>
          <section className='space-y-3'>
            <h3 className='text-sm font-semibold'>Runtime Prompting</h3>
            <p className='text-xs text-zinc-500'>
              Prompt assembly order: Global policy → Workspace files → User system instruction. Hidden safety baseline policy is always enforced server-side.
            </p>
            <div className='space-y-2 rounded-xl border border-[#2a2a2a] bg-[#111] p-3'>
              <label htmlFor='user-system-instruction' className='text-xs font-medium text-zinc-300'>
                User System Instruction
              </label>
              <p className='text-[11px] text-zinc-500'>
                This instruction applies to your runtime only. Do not paste secrets or third-party private data you are not authorized to process.
              </p>
              <textarea
                id='user-system-instruction'
                value={settings.systemInstruction}
                onChange={(event) => onPatch({ systemInstruction: event.target.value })}
                rows={5}
                className='w-full rounded border border-[#2a2a2a] bg-[#0c0c0c] px-3 py-2 text-xs text-zinc-100'
                placeholder='Add personal operating preferences and constraints for your agent.'
              />
              {!settings.systemInstruction.trim() && (
                <p className='text-[11px] text-amber-300'>Warning: User system instruction is empty.</p>
              )}
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
            <div>
              <p className='text-xs font-semibold text-zinc-200'>Thinking effort</p>
              <p className='text-[11px] text-zinc-500'>Only provider/model-supported effort levels are shown. Some native-thinking models do not expose a configurable effort knob.</p>
            </div>
            <label htmlFor='agent-thinking-effort' className='sr-only'>
              Thinking effort
            </label>
            <select
              id='agent-thinking-effort'
              value={selectedReasoningEffort}
              onChange={(event) => {
                const effort = event.target.value as ReasoningEffort
                onPatch({ reasoningEffort: effort, enableReasoning: effort !== 'none' })
              }}
              disabled={!canConfigureReasoning}
              className='mt-3 w-full rounded border border-[#2a2a2a] bg-[#111] px-3 py-2 text-xs text-zinc-100 disabled:cursor-not-allowed disabled:text-zinc-600'
            >
              {availableReasoningEfforts.map((effort) => (
                <option key={effort} value={effort} className='bg-[#111] text-zinc-100'>
                  {THINKING_EFFORT_LABELS[effort]}
                </option>
              ))}
            </select>
          </div>
        )}
          </section>

      <section className='space-y-2'>
        <h3 className='text-sm font-semibold'>Behavior</h3>
        <Toggle label='Verbose logging' checked={settings.verboseLogging} onToggle={(value) => onPatch({ verboseLogging: value })} />
        <Toggle label='Confirm destructive actions' checked={settings.confirmDestructiveActions} onToggle={(value) => onPatch({ confirmDestructiveActions: value })} />
      </section>

          <section className='space-y-3'>
        <div>
          <h3 className='text-sm font-semibold'>Tools & Permissions</h3>
          <p className='mt-1 text-xs text-zinc-500'>Control which tools Aegis can use and whether each requires your approval before running.</p>
        </div>
        <ToolsTab settings={settings} onPatch={onPatch} />
          </section>
        </>
      )}
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
