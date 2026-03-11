import { useState } from 'react'
import { BrandIcon, Icons } from '../icons'
import { maskSecret, type AuthType, type CustomServerForm, type IntegrationConfig } from '../../lib/mcp'

type IntegrationsTabProps = {
  integrations: IntegrationConfig[]
  onChange: (integrations: IntegrationConfig[]) => void
}

type TelegramStatus = {
  username: string
  id: number
  deliveryMode: 'webhook' | 'polling'
  lastHealthCheck: string
  pendingUpdates: number
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
  const [telegramToken, setTelegramToken] = useState('')
  const [telegramChatId, setTelegramChatId] = useState('')
  const [telegramTestText, setTelegramTestText] = useState('Aegis Telegram draft test message')
  const [telegramMode, setTelegramMode] = useState<'webhook' | 'polling'>('polling')
  const [telegramWebhookUrl, setTelegramWebhookUrl] = useState('')
  const [telegramSecret, setTelegramSecret] = useState('')
  const [telegramStatus, setTelegramStatus] = useState<TelegramStatus | null>(null)
  const [telegramResult, setTelegramResult] = useState('')

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

  const connectTelegram = async () => {
    const response = await fetch('/api/integrations/telegram/register/default', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bot_token: telegramToken, delivery_mode: telegramMode, webhook_url: telegramWebhookUrl, webhook_secret: telegramSecret }),
    })
    const data = await response.json()
    if (!response.ok) {
      setTelegramResult(data.detail ?? 'Connect failed')
      updateIntegration('telegram', { status: 'error' })
      return
    }
    setTelegramStatus({
      username: data.bot?.username ?? 'unknown',
      id: data.bot?.id ?? 0,
      deliveryMode: telegramMode,
      lastHealthCheck: new Date().toISOString(),
      pendingUpdates: 0,
    })
    setTelegramResult('Connected')
    updateIntegration('telegram', { status: 'connected', enabled: true, apiKeyMasked: maskSecret(telegramToken), lastCheckedAt: new Date().toISOString() })
  }

  const testTelegram = async () => {
    const response = await fetch('/api/integrations/telegram/default/test', { method: 'POST' })
    const data = await response.json()
    if (!response.ok) {
      setTelegramResult(data.detail ?? 'Test failed')
      return
    }
    setTelegramStatus({
      username: data.bot?.username ?? 'unknown',
      id: data.bot?.id ?? 0,
      deliveryMode: data.delivery_mode ?? telegramMode,
      lastHealthCheck: new Date().toISOString(),
      pendingUpdates: data.webhook?.pending_update_count ?? 0,
    })
    setTelegramResult(JSON.stringify(data, null, 2))
  }

  const sendDraftTest = async () => {
    const response = await fetch('/api/integrations/telegram/default/send_draft', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chat_id: Number(telegramChatId), text: telegramTestText }),
    })
    const data = await response.json()
    setTelegramResult(JSON.stringify(data, null, 2))
  }

  const sendMessageTest = async () => {
    const response = await fetch('/api/integrations/telegram/default/send_message', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chat_id: Number(telegramChatId), text: telegramTestText }),
    })
    const data = await response.json()
    setTelegramResult(JSON.stringify(data, null, 2))
  }

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

              {isExpanded && integration.id !== 'telegram' && (
                <div className='mt-3 rounded-lg border border-[#2a2a2a] bg-[#0d0d0d] p-3 text-xs'>
                  <p className='text-zinc-400'>Auth method: {integration.authType ?? 'none'}</p>
                  <p className='text-zinc-400'>Endpoint: {integration.serverUrl ?? 'managed integration'}</p>
                  <p className='text-zinc-400'>Scopes: {(integration.scopes ?? []).join(', ') || 'none'}</p>
                  <p className='mt-2 text-zinc-500'>Available tools: {integration.tools.join(', ')}</p>
                </div>
              )}

              {isExpanded && integration.id === 'telegram' && (
                <div className='mt-3 space-y-3 rounded-lg border border-[#2a2a2a] bg-[#0d0d0d] p-3 text-xs'>
                  <div className='grid gap-2 md:grid-cols-2'>
                    <input type='password' placeholder='Bot token' value={telegramToken} onChange={(event) => setTelegramToken(event.target.value)} className='rounded border border-[#2a2a2a] bg-black/40 px-2 py-1.5' />
                    <input placeholder='Webhook URL (optional)' value={telegramWebhookUrl} onChange={(event) => setTelegramWebhookUrl(event.target.value)} className='rounded border border-[#2a2a2a] bg-black/40 px-2 py-1.5' />
                    <input placeholder='Webhook secret (optional)' value={telegramSecret} onChange={(event) => setTelegramSecret(event.target.value)} className='rounded border border-[#2a2a2a] bg-black/40 px-2 py-1.5' />
                    <select value={telegramMode} onChange={(event) => setTelegramMode(event.target.value as 'webhook' | 'polling')} className='rounded border border-[#2a2a2a] bg-black/40 px-2 py-1.5'>
                      <option value='polling'>Polling</option>
                      <option value='webhook'>Webhook</option>
                    </select>
                  </div>

                  <div className='flex flex-wrap gap-2'>
                    <button type='button' onClick={connectTelegram} className='rounded border border-[#2a2a2a] px-2 py-1'>Connect</button>
                    <button type='button' onClick={testTelegram} className='rounded border border-[#2a2a2a] px-2 py-1'>Get Me / Test</button>
                    <button type='button' onClick={() => { setTelegramStatus(null); setTelegramResult('Disconnected') }} className='rounded border border-[#2a2a2a] px-2 py-1'>Disconnect</button>
                  </div>

                  <div className='grid gap-2 md:grid-cols-[1fr_2fr]'>
                    <input placeholder='chat_id' value={telegramChatId} onChange={(event) => setTelegramChatId(event.target.value)} className='rounded border border-[#2a2a2a] bg-black/40 px-2 py-1.5' />
                    <input placeholder='Test message text' value={telegramTestText} onChange={(event) => setTelegramTestText(event.target.value)} className='rounded border border-[#2a2a2a] bg-black/40 px-2 py-1.5' />
                  </div>

                  <div className='flex flex-wrap gap-2'>
                    <button type='button' onClick={sendDraftTest} className='rounded border border-[#2a2a2a] px-2 py-1'>Send Draft Test</button>
                    <button type='button' onClick={sendMessageTest} className='rounded border border-[#2a2a2a] px-2 py-1'>Send Message Test</button>
                  </div>

                  <div className='rounded border border-[#2a2a2a] bg-black/30 p-2'>
                    <p>Bot: @{telegramStatus?.username ?? 'n/a'} ({telegramStatus?.id ?? '-'})</p>
                    <p>Delivery mode: {telegramStatus?.deliveryMode ?? telegramMode}</p>
                    <p>Last health check: {telegramStatus?.lastHealthCheck ?? 'n/a'}</p>
                    <p>Pending updates: {telegramStatus?.pendingUpdates ?? 0}</p>
                    <p>Webhook secret: {telegramSecret ? 'Configured' : 'Not set'}</p>
                  </div>

                  <pre className='max-h-36 overflow-auto rounded border border-[#2a2a2a] bg-black/40 p-2 text-[11px] text-zinc-300'>{telegramResult || 'No test output yet.'}</pre>
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
