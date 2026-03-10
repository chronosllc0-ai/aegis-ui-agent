import { useState } from 'react'
import { BrandIcon, Icons } from '../icons'
import { maskSecret, type AuthType, type CustomServerForm, type IntegrationConfig } from '../../lib/mcp'

type IntegrationsTabProps = {
  integrations: IntegrationConfig[]
  onChange: (integrations: IntegrationConfig[]) => void
}

const EMPTY_FORM: CustomServerForm = { serverName: '', serverUrl: '', authType: 'none', apiKey: '' }

const STATUS_META: Record<IntegrationConfig['status'], { tone: string; label: string }> = {
  connected: { tone: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30', label: 'Connected' },
  error: { tone: 'bg-red-500/20 text-red-300 border-red-500/30', label: 'Error' },
  disabled: { tone: 'bg-zinc-700/20 text-zinc-300 border-zinc-700/40', label: 'Not Connected' },
  needs_auth: { tone: 'bg-amber-500/20 text-amber-300 border-amber-500/30', label: 'Needs Auth' },
}

export function IntegrationsTab({ integrations, onChange }: IntegrationsTabProps) {
  const [form, setForm] = useState<CustomServerForm>(EMPTY_FORM)
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const updateIntegration = (id: string, patch: Partial<IntegrationConfig>) => {
    onChange(integrations.map((integration) => (integration.id === id ? { ...integration, ...patch } : integration)))
  }

  const addCustom = () => {
    if (!form.serverName || !form.serverUrl) return
    const next: IntegrationConfig = {
      id: crypto.randomUUID(),
      name: form.serverName,
      icon: 'mcp',
      description: `Custom MCP server at ${form.serverUrl}`,
      enabled: true,
      status: 'connected',
      authType: form.authType,
      serverUrl: form.serverUrl,
      apiKeyMasked: maskSecret(form.apiKey),
      tools: ['custom_tool'],
      scopes: ['Custom MCP scope'],
      lastCheckedAt: new Date().toISOString(),
    }
    onChange([...integrations, next])
    setForm(EMPTY_FORM)
  }

  const mcpServers = integrations.filter((integration) => integration.serverUrl)

  return (
    <div className='mx-auto max-w-5xl space-y-6'>
      <header>
        <h3 className='text-lg font-semibold'>Integrations</h3>
        <p className='text-sm text-zinc-400'>Connect messaging and tool integrations so Aegis can complete cross-platform workflows.</p>
      </header>

      <section className='grid gap-3 lg:grid-cols-2'>
        {integrations.map((integration) => {
          const status = STATUS_META[integration.status]
          const isExpanded = expandedId === integration.id
          return (
            <article key={integration.id} className='rounded-2xl border border-[#2a2a2a] bg-[#111] p-4'>
              <div className='flex items-start justify-between gap-3'>
                <div>
                  <p className='inline-flex items-center gap-2 text-sm font-medium'><BrandIcon id={integration.icon} className='h-5 w-5' /> {integration.name}</p>
                  <p className='mt-1 text-xs text-zinc-400'>{integration.description}</p>
                </div>
                <span className={`rounded-full border px-2 py-1 text-[11px] ${status.tone}`}>{status.label}</span>
              </div>
              <div className='mt-2 text-[11px] text-zinc-500'>
                <p>Last checked: {integration.lastCheckedAt ?? 'n/a'}</p>
                <p>Last used: {integration.lastUsedAt ?? 'n/a'}</p>
                <p>Tools: {integration.tools.length}</p>
              </div>
              <div className='mt-3 flex flex-wrap gap-2 text-xs'>
                <button type='button' onClick={() => updateIntegration(integration.id, { enabled: !integration.enabled, status: integration.enabled ? 'disabled' : 'connected' })} className='inline-flex items-center gap-1 rounded-md border border-[#2a2a2a] px-2 py-1'>
                  {Icons.settings({ className: 'h-3.5 w-3.5' })}
                  {integration.enabled ? 'Disable' : 'Connect'}
                </button>
                <button type='button' onClick={() => updateIntegration(integration.id, { status: integration.status === 'error' ? 'connected' : integration.status })} className='inline-flex items-center gap-1 rounded-md border border-[#2a2a2a] px-2 py-1'>{Icons.check({ className: 'h-3.5 w-3.5' })}Test</button>
                <button type='button' onClick={() => setExpandedId(isExpanded ? null : integration.id)} className='inline-flex items-center gap-1 rounded-md border border-[#2a2a2a] px-2 py-1'>{isExpanded ? Icons.chevronDown({ className: 'h-3.5 w-3.5' }) : Icons.chevronRight({ className: 'h-3.5 w-3.5' })}{isExpanded ? 'Hide details' : 'Details'}</button>
              </div>

              {isExpanded && (
                <div className='mt-3 rounded-lg border border-[#2a2a2a] bg-[#0d0d0d] p-3 text-xs'>
                  <p className='text-zinc-400'>Auth method: {integration.authType ?? 'none'}</p>
                  <p className='text-zinc-400'>Endpoint: {integration.serverUrl ?? 'managed integration'}</p>
                  <p className='text-zinc-400'>Scopes: {(integration.scopes ?? []).join(', ') || 'none'}</p>
                  <p className='mt-2 text-zinc-500'>Available tools: {integration.tools.join(', ')}</p>
                </div>
              )}
            </article>
          )
        })}
      </section>

      <section className='rounded-2xl border border-[#2a2a2a] bg-[#111] p-4'>
        <h4 className='mb-2 inline-flex items-center gap-2 text-sm font-semibold'>{Icons.workflows({ className: 'h-4 w-4' })}MCP Servers</h4>
        {mcpServers.length === 0 ? (
          <p className='text-xs text-zinc-500'>No custom MCP servers registered yet.</p>
        ) : (
          <div className='space-y-2 text-xs'>
            {mcpServers.map((server) => (
              <div key={server.id} className='rounded-lg border border-[#2a2a2a] bg-[#0d0d0d] p-2'>
                <p className='font-medium text-zinc-200'>{server.name}</p>
                <p className='text-zinc-500'>URL: {server.serverUrl}</p>
                <p className='text-zinc-500'>Auth: {server.authType ?? 'none'} · Tools: {server.tools.length}</p>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className='rounded-2xl border border-[#2a2a2a] bg-[#111] p-4'>
        <h4 className='mb-2 inline-flex items-center gap-2 text-sm font-semibold'>{Icons.plus({ className: 'h-4 w-4' })}Add MCP Server</h4>
        <div className='grid gap-2 md:grid-cols-2'>
          <input placeholder='Server name' value={form.serverName} onChange={(event) => setForm((prev) => ({ ...prev, serverName: event.target.value }))} className='rounded-lg border border-[#2a2a2a] bg-[#0c0c0c] px-3 py-2 text-sm' />
          <input placeholder='Server URL (http://localhost:3000/mcp)' value={form.serverUrl} onChange={(event) => setForm((prev) => ({ ...prev, serverUrl: event.target.value }))} className='rounded-lg border border-[#2a2a2a] bg-[#0c0c0c] px-3 py-2 text-sm' />
          <select value={form.authType} onChange={(event) => setForm((prev) => ({ ...prev, authType: event.target.value as AuthType }))} className='rounded-lg border border-[#2a2a2a] bg-[#0c0c0c] px-3 py-2 text-sm'>
            <option value='none'>None</option>
            <option value='api_key'>API Key</option>
            <option value='oauth'>OAuth</option>
          </select>
          <input placeholder='API Key (optional)' value={form.apiKey} onChange={(event) => setForm((prev) => ({ ...prev, apiKey: event.target.value }))} className='rounded-lg border border-[#2a2a2a] bg-[#0c0c0c] px-3 py-2 text-sm' />
        </div>
        <div className='mt-3 flex gap-2 text-xs'>
          <button type='button' className='inline-flex items-center gap-1 rounded-md border border-[#2a2a2a] px-3 py-1.5'>{Icons.check({ className: 'h-3.5 w-3.5' })}Test Connection</button>
          <button type='button' onClick={addCustom} className='inline-flex items-center gap-1 rounded-md bg-blue-600 px-3 py-1.5'>{Icons.plus({ className: 'h-3.5 w-3.5' })}Add MCP Server</button>
        </div>
      </section>
    </div>
  )
}
