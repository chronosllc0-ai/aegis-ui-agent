import { useEffect, useState } from 'react'
import { BrandIcon, Icons } from '../icons'
import type { CustomServerForm, IntegrationConfig } from '../../lib/mcp'
import {
  addMcpServer,
  connectNative,
  deleteMcpServer,
  disconnectNative,
  executeNative,
  fetchIntegrations,
  mergeNativeIntoSettings,
  testMcpServer,
  testNative,
  type MCPServerResponse,
} from '../../lib/integrationsApi'

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

const DEFAULT_SECRET_KEYS: Record<string, string> = {
  telegram: 'bot_token',
  slack: 'bot_token',
  discord: 'bot_token',
  'brave-search': 'api_key',
}

export function IntegrationsTab({ integrations, onChange }: IntegrationsTabProps) {
  const [form, setForm] = useState<CustomServerForm>(EMPTY_FORM)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [credentials, setCredentials] = useState<Record<string, string>>({})
  const [testResult, setTestResult] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState<string | null>(null)
  const [mcpServers, setMcpServers] = useState<MCPServerResponse[]>([])

  const nativeIntegrations = integrations.filter((integration) => !integration.serverUrl)

  const refresh = async () => {
    const data = await fetchIntegrations()
    onChange(mergeNativeIntoSettings(integrations, data.native))
    setMcpServers(data.mcp)
  }

  useEffect(() => {
    refresh().catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const runAction = async (key: string, action: () => Promise<void>) => {
    setLoading(key)
    setError(null)
    try {
      await action()
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Integration action failed')
    } finally {
      setLoading(null)
    }
  }

  return (
    <div className='mx-auto max-w-5xl space-y-6'>
      <header>
        <h3 className='text-lg font-semibold'>Integrations</h3>
        <p className='text-sm text-zinc-400'>Native Integrations are first-party connectors. Custom MCP Servers are user-provided remote or local tool servers.</p>
      </header>

      {error && <div className='rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-200'>{error}</div>}

      <section className='space-y-3'>
        <h4 className='text-sm font-semibold text-zinc-200'>Native Integrations</h4>
        <div className='grid gap-3 lg:grid-cols-2'>
          {nativeIntegrations.map((integration) => {
            const status = STATUS_META[integration.status]
            const isExpanded = expandedId === integration.id
            const secretKey = DEFAULT_SECRET_KEYS[integration.id] ?? 'token'
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

                <div className='mt-2 flex gap-2'>
                  <input
                    value={credentials[integration.id] ?? ''}
                    onChange={(event) => setCredentials((prev) => ({ ...prev, [integration.id]: event.target.value }))}
                    placeholder={`Enter ${secretKey} (stored masked)`}
                    className='flex-1 rounded-md border border-[#2a2a2a] bg-[#0d0d0d] px-2 py-1 text-xs'
                  />
                </div>

                <div className='mt-3 flex flex-wrap gap-2 text-xs'>
                  <button
                    type='button'
                    onClick={() => runAction(`connect-${integration.id}`, () => connectNative(integration.id, integration.id === 'filesystem' ? { roots: ['.'], allow_delete: false } : integration.id === 'code-exec' ? { enabled: true } : {}, credentials[integration.id] ? { [secretKey]: credentials[integration.id] } : {}))}
                    className='inline-flex items-center gap-1 rounded-md border border-[#2a2a2a] px-2 py-1'
                  >
                    {Icons.check({ className: 'h-3.5 w-3.5' })}
                    Connect
                  </button>
                  <button type='button' onClick={() => runAction(`test-${integration.id}`, () => testNative(integration.id))} className='inline-flex items-center gap-1 rounded-md border border-[#2a2a2a] px-2 py-1'>{Icons.search({ className: 'h-3.5 w-3.5' })}Test</button>
                  <button type='button' onClick={() => runAction(`exec-${integration.id}`, async () => { const data = await executeNative(integration.id, integration.id === 'brave-search' ? 'brave.web_search' : integration.id === 'filesystem' ? 'filesystem.list_dir' : integration.id === 'code-exec' ? 'code.exec_python' : integration.id === 'telegram' ? 'telegram.get_me' : integration.id === 'slack' ? 'slack.auth_test' : 'discord.get_me', integration.id === 'brave-search' ? { q: 'Aegis UI navigator' } : integration.id === 'code-exec' ? { code: 'print("ok")' } : {}); setTestResult((prev) => ({ ...prev, [integration.id]: JSON.stringify(data).slice(0, 240) })) })} className='inline-flex items-center gap-1 rounded-md border border-[#2a2a2a] px-2 py-1'>{Icons.play({ className: 'h-3.5 w-3.5' })}Run tool test</button>
                  <button type='button' onClick={() => runAction(`disconnect-${integration.id}`, () => disconnectNative(integration.id))} className='inline-flex items-center gap-1 rounded-md border border-[#2a2a2a] px-2 py-1'>{Icons.close({ className: 'h-3.5 w-3.5' })}Disconnect</button>
                  <button type='button' onClick={() => setExpandedId(isExpanded ? null : integration.id)} className='inline-flex items-center gap-1 rounded-md border border-[#2a2a2a] px-2 py-1'>{isExpanded ? Icons.chevronDown({ className: 'h-3.5 w-3.5' }) : Icons.chevronRight({ className: 'h-3.5 w-3.5' })}{isExpanded ? 'Hide details' : 'Details'}</button>
                </div>
                {loading?.includes(integration.id) && <p className='mt-2 text-[11px] text-zinc-500'>Working…</p>}
                {testResult[integration.id] && <pre className='mt-2 overflow-x-auto rounded bg-[#0a0a0a] p-2 text-[11px] text-zinc-400'>{testResult[integration.id]}</pre>}

                {isExpanded && (
                  <div className='mt-3 rounded-lg border border-[#2a2a2a] bg-[#0d0d0d] p-3 text-xs'>
                    <p className='text-zinc-400'>Masked credentials: {Object.values(integration.settings ?? {}).join(', ') || 'none saved'}</p>
                    <p className='mt-2 text-zinc-500'>Available tools: {integration.tools.join(', ')}</p>
                  </div>
                )}
              </article>
            )
          })}
        </div>
      </section>

      <section className='rounded-2xl border border-[#2a2a2a] bg-[#111] p-4'>
        <h4 className='mb-2 inline-flex items-center gap-2 text-sm font-semibold'>{Icons.workflows({ className: 'h-4 w-4' })}Custom MCP Servers</h4>
        {mcpServers.length === 0 ? (
          <p className='text-xs text-zinc-500'>No custom MCP servers registered yet.</p>
        ) : (
          <div className='space-y-2 text-xs'>
            {mcpServers.map((server) => (
              <div key={server.server_id} className='rounded-lg border border-[#2a2a2a] bg-[#0d0d0d] p-2'>
                <p className='font-medium text-zinc-200'>{server.name} · {server.transport}</p>
                <p className='text-zinc-400'>Tool count: {server.tool_count} · Last test: {server.last_test_at ?? 'n/a'}</p>
                <p className='text-zinc-500'>{server.config_summary?.url ?? server.config_summary?.command ?? ''}</p>
                <div className='mt-2 flex gap-2'>
                  <button type='button' onClick={() => runAction(`mcp-test-${server.server_id}`, () => testMcpServer(server.server_id))} className='rounded border border-[#2a2a2a] px-2 py-1'>Test</button>
                  <button type='button' onClick={() => runAction(`mcp-del-${server.server_id}`, () => deleteMcpServer(server.server_id))} className='rounded border border-[#2a2a2a] px-2 py-1'>Disconnect</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className='rounded-2xl border border-dashed border-[#2a2a2a] bg-[#0f0f0f] p-4'>
        <h4 className='text-sm font-semibold'>Add Custom MCP Server</h4>
        <div className='mt-3 grid gap-2 sm:grid-cols-2'>
          <input value={form.serverName} onChange={(event) => setForm((prev) => ({ ...prev, serverName: event.target.value }))} placeholder='Server name' className='rounded-md border border-[#2a2a2a] bg-[#090909] px-2 py-1 text-sm' />
          <input value={form.serverUrl} onChange={(event) => setForm((prev) => ({ ...prev, serverUrl: event.target.value }))} placeholder='Server URL' className='rounded-md border border-[#2a2a2a] bg-[#090909] px-2 py-1 text-sm' />
          <select value={form.authType} onChange={(event) => setForm((prev) => ({ ...prev, authType: event.target.value as CustomServerForm['authType'] }))} className='rounded-md border border-[#2a2a2a] bg-[#090909] px-2 py-1 text-sm'>
            <option value='none'>No auth</option>
            <option value='api_key'>API key</option>
            <option value='oauth'>OAuth/Bearer</option>
          </select>
          <input value={form.apiKey} onChange={(event) => setForm((prev) => ({ ...prev, apiKey: event.target.value }))} placeholder='API/Bearer token' className='rounded-md border border-[#2a2a2a] bg-[#090909] px-2 py-1 text-sm' />
        </div>
        <div className='mt-3 flex gap-2 text-xs'>
          <button
            type='button'
            onClick={() => runAction('mcp-add', () => addMcpServer({ name: form.serverName, transport: 'streamable_http', config: { url: form.serverUrl }, secrets: form.apiKey ? { bearer_token: form.apiKey } : {} }))}
            className='inline-flex items-center gap-1 rounded-md border border-[#2a2a2a] px-2 py-1'
          >
            {Icons.plus({ className: 'h-3.5 w-3.5' })}
            Add server
          </button>
        </div>
      </section>
    </div>
  )
}
