import { useState } from 'react'
import { maskSecret, type AuthType, type CustomServerForm, type IntegrationConfig } from '../../lib/mcp'

type IntegrationsTabProps = {
  integrations: IntegrationConfig[]
  onChange: (integrations: IntegrationConfig[]) => void
}

const EMPTY_FORM: CustomServerForm = { serverName: '', serverUrl: '', authType: 'none', apiKey: '' }

const STATUS_DOT: Record<IntegrationConfig['status'], string> = {
  connected: 'bg-emerald-400',
  error: 'bg-red-400',
  disabled: 'bg-zinc-500',
}

export function IntegrationsTab({ integrations, onChange }: IntegrationsTabProps) {
  const [form, setForm] = useState<CustomServerForm>(EMPTY_FORM)

  const updateIntegration = (id: string, patch: Partial<IntegrationConfig>) => {
    onChange(integrations.map((integration) => (integration.id === id ? { ...integration, ...patch } : integration)))
  }

  const addCustom = () => {
    if (!form.serverName || !form.serverUrl) return
    const next: IntegrationConfig = {
      id: crypto.randomUUID(),
      name: form.serverName,
      icon: '➕',
      description: `Custom MCP server at ${form.serverUrl}`,
      enabled: true,
      status: 'connected',
      authType: form.authType,
      serverUrl: form.serverUrl,
      apiKeyMasked: maskSecret(form.apiKey),
      tools: ['custom_tool'],
    }
    onChange([...integrations, next])
    setForm(EMPTY_FORM)
  }

  return (
    <div className='space-y-6'>
      <section>
        <h3 className='mb-2 text-sm font-semibold'>Connected Integrations</h3>
        <div className='space-y-2'>
          {integrations.map((integration) => (
            <article key={integration.id} className='rounded border border-[#2a2a2a] bg-[#111] p-3'>
              <div className='flex items-start justify-between gap-4'>
                <div>
                  <p className='font-medium'>{integration.icon} {integration.name}</p>
                  <p className='text-xs text-zinc-400'>{integration.description}</p>
                  <p className='mt-1 text-[11px] text-zinc-500'>Tools: {integration.tools.join(', ')}</p>
                </div>
                <span className='inline-flex items-center gap-2 text-xs'>
                  <span className={`h-2.5 w-2.5 rounded-full ${STATUS_DOT[integration.status]}`} />
                  {integration.status}
                </span>
              </div>
              <div className='mt-2 flex gap-2 text-xs'>
                <button type='button' onClick={() => updateIntegration(integration.id, { enabled: !integration.enabled, status: integration.enabled ? 'disabled' : 'connected' })} className='rounded border border-[#2a2a2a] px-2 py-1'>
                  {integration.enabled ? 'Disable' : 'Enable'}
                </button>
                <button type='button' className='rounded border border-[#2a2a2a] px-2 py-1'>Configure</button>
                <button type='button' onClick={() => updateIntegration(integration.id, { status: 'connected' })} className='rounded border border-[#2a2a2a] px-2 py-1'>Test</button>
                <button type='button' onClick={() => onChange(integrations.filter((item) => item.id !== integration.id))} className='rounded border border-red-500/40 px-2 py-1 text-red-300'>Disconnect</button>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section>
        <h3 className='mb-2 text-sm font-semibold'>Add Integration</h3>
        <div className='grid gap-2 md:grid-cols-2'>
          <input placeholder='Server name' value={form.serverName} onChange={(event) => setForm((prev) => ({ ...prev, serverName: event.target.value }))} className='rounded border border-[#2a2a2a] bg-[#111] px-3 py-2' />
          <input placeholder='Server URL (http://localhost:3000/mcp)' value={form.serverUrl} onChange={(event) => setForm((prev) => ({ ...prev, serverUrl: event.target.value }))} className='rounded border border-[#2a2a2a] bg-[#111] px-3 py-2' />
          <select value={form.authType} onChange={(event) => setForm((prev) => ({ ...prev, authType: event.target.value as AuthType }))} className='rounded border border-[#2a2a2a] bg-[#111] px-3 py-2'>
            <option value='none'>None</option>
            <option value='api_key'>API Key</option>
            <option value='oauth'>OAuth</option>
          </select>
          <input placeholder='API Key (optional)' value={form.apiKey} onChange={(event) => setForm((prev) => ({ ...prev, apiKey: event.target.value }))} className='rounded border border-[#2a2a2a] bg-[#111] px-3 py-2' />
        </div>
        <div className='mt-2 flex gap-2 text-xs'>
          <button type='button' className='rounded border border-[#2a2a2a] px-2 py-1'>Test Connection</button>
          <button type='button' onClick={addCustom} className='rounded bg-blue-600 px-3 py-1'>Save</button>
        </div>
      </section>
    </div>
  )
}
