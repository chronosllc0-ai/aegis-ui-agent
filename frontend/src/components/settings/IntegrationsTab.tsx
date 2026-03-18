import { useState } from 'react'
import { maskSecret, renderIntegrationIcon, type AuthType, type CustomServerForm, type IntegrationConfig } from '../../lib/mcp'
import { BrandIcon } from '../icons'
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
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [integrationErrors, setIntegrationErrors] = useState<Record<string, string | null>>({})

  const renderIcon = (icon: string, name: string) => {
    if (icon.startsWith('http')) {
      return <img src={icon} alt={`${name} icon`} className='h-4 w-4 rounded-sm' />
    }
    return <BrandIcon id={icon} className='h-4 w-4' />
  }

  const updateIntegration = (id: string, patch: Partial<IntegrationConfig>) => {
    onChange(integrations.map((integration) => (integration.id === id ? { ...integration, ...patch } : integration)))
  }

  const setIntegrationError = (id: string, message: string | null) => {
    setIntegrationErrors((prev) => ({ ...prev, [id]: message }))
  }

  const postJson = async (path: string, payload: Record<string, unknown>) => {
    const response = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) {
      const detail = typeof data?.detail === 'string' ? data.detail : 'Request failed'
      throw new Error(detail)
    }
    return data
  }

  const connectTelegram = async (integration: IntegrationConfig) => {
    const settings = integration.settings ?? {}
    const payload = {
      bot_token: settings.bot_token ?? '',
      delivery_mode: settings.delivery_mode ?? 'polling',
      webhook_url: settings.webhook_url ?? '',
      webhook_secret: settings.webhook_secret ?? '',
    }
    if (!payload.bot_token) {
      updateIntegration(integration.id, { status: 'error', enabled: false })
      setIntegrationError(integration.id, 'Bot token is required.')
      return
    }
    setBusyId(integration.id)
    setIntegrationError(integration.id, null)
    try {
      const data = await postJson(`/api/integrations/telegram/register/${integration.id}`, payload)
      const connected = Boolean(data?.connection?.connected)
      updateIntegration(integration.id, { status: connected ? 'connected' : 'error', enabled: connected })
      if (!connected) setIntegrationError(integration.id, 'Connection failed.')
    } catch (err) {
      updateIntegration(integration.id, { status: 'error' })
      setIntegrationError(integration.id, err instanceof Error ? err.message : 'Connection failed.')
    } finally {
      setBusyId(null)
    }
  }

  const connectSlack = async (integration: IntegrationConfig) => {
    const settings = integration.settings ?? {}
    const payload = {
      bot_token: settings.bot_token ?? '',
      oauth_token: settings.oauth_token ?? '',
      workspace: settings.workspace ?? '',
    }
    if (!payload.bot_token && !payload.oauth_token) {
      updateIntegration(integration.id, { status: 'error', enabled: false })
      setIntegrationError(integration.id, 'Bot token or OAuth token is required.')
      return
    }
    setBusyId(integration.id)
    setIntegrationError(integration.id, null)
    try {
      const data = await postJson(`/api/integrations/slack/register/${integration.id}`, payload)
      const connected = Boolean(data?.connection?.connected)
      updateIntegration(integration.id, { status: connected ? 'connected' : 'error', enabled: connected })
      if (!connected) setIntegrationError(integration.id, 'Connection failed.')
    } catch (err) {
      updateIntegration(integration.id, { status: 'error' })
      setIntegrationError(integration.id, err instanceof Error ? err.message : 'Connection failed.')
    } finally {
      setBusyId(null)
    }
  }

  const connectDiscord = async (integration: IntegrationConfig) => {
    const settings = integration.settings ?? {}
    const payload = {
      bot_token: settings.bot_token ?? '',
      guild_id: settings.guild_id ?? '',
    }
    if (!payload.bot_token) {
      updateIntegration(integration.id, { status: 'error', enabled: false })
      setIntegrationError(integration.id, 'Bot token is required.')
      return
    }
    setBusyId(integration.id)
    setIntegrationError(integration.id, null)
    try {
      const data = await postJson(`/api/integrations/discord/register/${integration.id}`, payload)
      const connected = Boolean(data?.connection?.connected)
      updateIntegration(integration.id, { status: connected ? 'connected' : 'error', enabled: connected })
      if (!connected) setIntegrationError(integration.id, 'Connection failed.')
    } catch (err) {
      updateIntegration(integration.id, { status: 'error' })
      setIntegrationError(integration.id, err instanceof Error ? err.message : 'Connection failed.')
    } finally {
      setBusyId(null)
    }
  }

  const testTelegram = async (integration: IntegrationConfig) => {
    setBusyId(integration.id)
    setIntegrationError(integration.id, null)
    try {
      const data = await postJson(`/api/integrations/telegram/${integration.id}/test`, {})
      const ok = Boolean(data?.ok)
      updateIntegration(integration.id, { status: ok ? 'connected' : 'error' })
      if (!ok) setIntegrationError(integration.id, 'Telegram test failed.')
    } catch (err) {
      updateIntegration(integration.id, { status: 'error' })
      setIntegrationError(integration.id, err instanceof Error ? err.message : 'Telegram test failed.')
    } finally {
      setBusyId(null)
    }
  }

  const testSlack = async (integration: IntegrationConfig) => {
    setBusyId(integration.id)
    setIntegrationError(integration.id, null)
    try {
      const data = await postJson(`/api/integrations/slack/${integration.id}/test`, {})
      const ok = Boolean(data?.ok)
      updateIntegration(integration.id, { status: ok ? 'connected' : 'error' })
      if (!ok) setIntegrationError(integration.id, 'Slack test failed.')
    } catch (err) {
      updateIntegration(integration.id, { status: 'error' })
      setIntegrationError(integration.id, err instanceof Error ? err.message : 'Slack test failed.')
    } finally {
      setBusyId(null)
    }
  }

  const testDiscord = async (integration: IntegrationConfig) => {
    setBusyId(integration.id)
    setIntegrationError(integration.id, null)
    try {
      const data = await postJson(`/api/integrations/discord/${integration.id}/test`, {})
      const ok = Boolean(data?.ok)
      updateIntegration(integration.id, { status: ok ? 'connected' : 'error' })
      if (!ok) setIntegrationError(integration.id, 'Discord test failed.')
    } catch (err) {
      updateIntegration(integration.id, { status: 'error' })
      setIntegrationError(integration.id, err instanceof Error ? err.message : 'Discord test failed.')
    } finally {
      setBusyId(null)
    }
  }

  const toggleIntegration = async (integration: IntegrationConfig) => {
    if (integration.enabled) {
      updateIntegration(integration.id, { enabled: false, status: 'disabled' })
      setIntegrationError(integration.id, null)
      return
    }
    if (integration.id === 'telegram') {
      await connectTelegram(integration)
      return
    }
    if (integration.id === 'slack') {
      await connectSlack(integration)
      return
    }
    if (integration.id === 'discord') {
      await connectDiscord(integration)
      return
    }
    updateIntegration(integration.id, { enabled: true, status: 'disabled' })
  }

  const addCustom = () => {
    if (!form.serverName || !form.serverUrl) return
    const next: IntegrationConfig = {
      id: crypto.randomUUID(),
      name: form.serverName,
      icon: 'custom',
      description: `Custom MCP server at ${form.serverUrl}`,
      enabled: false,
      status: 'disabled',
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
          {integrations.map((integration) => {
            const isConfigurable = ['telegram', 'slack', 'discord'].includes(integration.id)
            const isBusy = busyId === integration.id
            const canTest = ['telegram', 'slack', 'discord'].includes(integration.id)
            const handleTest = () => {
              if (integration.id === 'telegram') return testTelegram(integration)
              if (integration.id === 'slack') return testSlack(integration)
              if (integration.id === 'discord') return testDiscord(integration)
              return undefined
            }
            return (
              <article key={integration.id} className='rounded border border-[#2a2a2a] bg-[#111] p-3'>
                <div className='flex items-start justify-between gap-4'>
                  <div>
                  <div className='flex items-center gap-2'>
                    {renderIntegrationIcon(integration.icon)}
                    <p className='font-medium'>{integration.name}</p>
                  </div>
                  <p className='text-xs text-zinc-400'>{integration.description}</p>
                  <p className='mt-1 text-[11px] text-zinc-500'>Tools: {integration.tools.join(', ')}</p>
                </div>
                  <span className='inline-flex items-center gap-2 text-xs'>
                  <span className={`h-2.5 w-2.5 rounded-full ${STATUS_DOT[integration.status]}`} />
                  {integration.status}
                </span>
                </div>
                <div className='mt-2 flex gap-2 text-xs'>
                <button
                  type='button'
                  onClick={() => toggleIntegration(integration)}
                  disabled={isBusy}
                  className={`rounded border border-[#2a2a2a] px-2 py-1 ${isBusy ? 'opacity-60' : ''}`}
                >
                  {integration.enabled ? 'Disable' : 'Enable'}
                </button>
                <button
                  type='button'
                  onClick={() => setExpandedId((prev) => (prev === integration.id ? null : integration.id))}
                  disabled={!isConfigurable}
                  className={`rounded border border-[#2a2a2a] px-2 py-1 ${!isConfigurable ? 'cursor-not-allowed opacity-60' : ''}`}
                  title={isConfigurable ? `Configure ${integration.name}` : 'Configuration not available'}
                >
                  Configure
                </button>
                <button
                  type='button'
                  onClick={handleTest}
                  disabled={!canTest || isBusy}
                  className={`rounded border border-[#2a2a2a] px-2 py-1 ${!canTest || isBusy ? 'cursor-not-allowed opacity-60' : ''}`}
                  title={canTest ? `Run ${integration.name} test` : 'Test not available'}
                >
                  Test
                </button>
                <button type='button' onClick={() => onChange(integrations.filter((item) => item.id !== integration.id))} className='rounded border border-red-500/40 px-2 py-1 text-red-300'>Disconnect</button>
                </div>
                {expandedId === integration.id && integration.id === 'telegram' && (
                <div className='mt-3 grid gap-2 text-xs'>
                  <input
                    placeholder='Bot token'
                    value={integration.settings?.bot_token ?? ''}
                    onChange={(event) =>
                      updateIntegration(integration.id, {
                        settings: { ...(integration.settings ?? {}), bot_token: event.target.value },
                      })
                    }
                    className='rounded border border-[#2a2a2a] bg-[#0f0f0f] px-3 py-2'
                  />
                  <label htmlFor={`integration-${integration.id}-delivery-mode`} className='sr-only'>
                    Delivery mode
                  </label>
                  <select
                    id={`integration-${integration.id}-delivery-mode`}
                    value={integration.settings?.delivery_mode ?? 'polling'}
                    onChange={(event) =>
                      updateIntegration(integration.id, {
                        settings: { ...(integration.settings ?? {}), delivery_mode: event.target.value },
                      })
                    }
                    className='rounded border border-[#2a2a2a] bg-[#0f0f0f] px-3 py-2'
                  >
                    <option value='polling'>Polling</option>
                    <option value='webhook'>Webhook</option>
                  </select>
                  <input
                    placeholder='Webhook URL (optional)'
                    value={integration.settings?.webhook_url ?? ''}
                    onChange={(event) =>
                      updateIntegration(integration.id, {
                        settings: { ...(integration.settings ?? {}), webhook_url: event.target.value },
                      })
                    }
                    className='rounded border border-[#2a2a2a] bg-[#0f0f0f] px-3 py-2'
                  />
                  <input
                    placeholder='Webhook secret (optional)'
                    value={integration.settings?.webhook_secret ?? ''}
                    onChange={(event) =>
                      updateIntegration(integration.id, {
                        settings: { ...(integration.settings ?? {}), webhook_secret: event.target.value },
                      })
                    }
                    className='rounded border border-[#2a2a2a] bg-[#0f0f0f] px-3 py-2'
                  />
                  <div className='flex gap-2'>
                    <button
                      type='button'
                      onClick={() => connectTelegram(integration)}
                      disabled={isBusy}
                      className={`rounded bg-blue-600 px-3 py-1 ${isBusy ? 'opacity-60' : ''}`}
                    >
                      Save & Connect
                    </button>
                    <button
                      type='button'
                      onClick={() => setExpandedId(null)}
                      className='rounded border border-[#2a2a2a] px-3 py-1'
                    >
                      Close
                    </button>
                  </div>
                </div>
              )}
                {expandedId === integration.id && integration.id === 'slack' && (
                <div className='mt-3 grid gap-2 text-xs'>
                  <input
                    placeholder='Bot token (optional)'
                    value={integration.settings?.bot_token ?? ''}
                    onChange={(event) =>
                      updateIntegration(integration.id, {
                        settings: { ...(integration.settings ?? {}), bot_token: event.target.value },
                      })
                    }
                    className='rounded border border-[#2a2a2a] bg-[#0f0f0f] px-3 py-2'
                  />
                  <input
                    placeholder='OAuth token (optional)'
                    value={integration.settings?.oauth_token ?? ''}
                    onChange={(event) =>
                      updateIntegration(integration.id, {
                        settings: { ...(integration.settings ?? {}), oauth_token: event.target.value },
                      })
                    }
                    className='rounded border border-[#2a2a2a] bg-[#0f0f0f] px-3 py-2'
                  />
                  <input
                    placeholder='Workspace (optional)'
                    value={integration.settings?.workspace ?? ''}
                    onChange={(event) =>
                      updateIntegration(integration.id, {
                        settings: { ...(integration.settings ?? {}), workspace: event.target.value },
                      })
                    }
                    className='rounded border border-[#2a2a2a] bg-[#0f0f0f] px-3 py-2'
                  />
                  <div className='flex gap-2'>
                    <button
                      type='button'
                      onClick={() => connectSlack(integration)}
                      disabled={isBusy}
                      className={`rounded bg-blue-600 px-3 py-1 ${isBusy ? 'opacity-60' : ''}`}
                    >
                      Save & Connect
                    </button>
                    <button
                      type='button'
                      onClick={() => setExpandedId(null)}
                      className='rounded border border-[#2a2a2a] px-3 py-1'
                    >
                      Close
                    </button>
                  </div>
                </div>
              )}
                {expandedId === integration.id && integration.id === 'discord' && (
                <div className='mt-3 grid gap-2 text-xs'>
                  <input
                    placeholder='Bot token'
                    value={integration.settings?.bot_token ?? ''}
                    onChange={(event) =>
                      updateIntegration(integration.id, {
                        settings: { ...(integration.settings ?? {}), bot_token: event.target.value },
                      })
                    }
                    className='rounded border border-[#2a2a2a] bg-[#0f0f0f] px-3 py-2'
                  />
                  <input
                    placeholder='Guild ID (optional)'
                    value={integration.settings?.guild_id ?? ''}
                    onChange={(event) =>
                      updateIntegration(integration.id, {
                        settings: { ...(integration.settings ?? {}), guild_id: event.target.value },
                      })
                    }
                    className='rounded border border-[#2a2a2a] bg-[#0f0f0f] px-3 py-2'
                  />
                  <div className='flex gap-2'>
                    <button
                      type='button'
                      onClick={() => connectDiscord(integration)}
                      disabled={isBusy}
                      className={`rounded bg-blue-600 px-3 py-1 ${isBusy ? 'opacity-60' : ''}`}
                    >
                      Save & Connect
                    </button>
                    <button
                      type='button'
                      onClick={() => setExpandedId(null)}
                      className='rounded border border-[#2a2a2a] px-3 py-1'
                    >
                      Close
                    </button>
                  </div>
                </div>
              )}
                {integrationErrors[integration.id] && (
                <p className='mt-2 text-xs text-red-300'>{integrationErrors[integration.id]}</p>
              )}
              </article>
            )
          })}
        </div>
      </section>

      <section>
        <h3 className='mb-2 text-sm font-semibold'>Add Integration</h3>
        <div className='grid gap-2 md:grid-cols-2'>
          <input placeholder='Server name' value={form.serverName} onChange={(event) => setForm((prev) => ({ ...prev, serverName: event.target.value }))} className='rounded border border-[#2a2a2a] bg-[#111] px-3 py-2' />
          <input placeholder='Server URL (http://localhost:3000/mcp)' value={form.serverUrl} onChange={(event) => setForm((prev) => ({ ...prev, serverUrl: event.target.value }))} className='rounded border border-[#2a2a2a] bg-[#111] px-3 py-2' />
          <label htmlFor='custom-integration-auth-type' className='sr-only'>
            Auth type
          </label>
          <select
            id='custom-integration-auth-type'
            value={form.authType}
            onChange={(event) => setForm((prev) => ({ ...prev, authType: event.target.value as AuthType }))}
            className='rounded border border-[#2a2a2a] bg-[#111] px-3 py-2'
          >
            <option value='none'>None</option>
            <option value='api_key'>API Key</option>
            <option value='oauth'>OAuth</option>
          </select>
          <input placeholder='API Key (optional)' value={form.apiKey} onChange={(event) => setForm((prev) => ({ ...prev, apiKey: event.target.value }))} className='rounded border border-[#2a2a2a] bg-[#111] px-3 py-2' />
        </div>
        <div className='mt-2 flex gap-2 text-xs'>
          <button type='button' disabled className='cursor-not-allowed rounded border border-[#2a2a2a] px-2 py-1 opacity-60' title='Backend endpoint not configured'>
            Test Connection
          </button>
          <button type='button' onClick={addCustom} className='rounded bg-blue-600 px-3 py-1'>Save</button>
        </div>
      </section>
    </div>
  )
}
