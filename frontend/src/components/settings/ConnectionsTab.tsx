import { useCallback, useEffect, useState } from 'react'
import { apiUrl } from '../../lib/api'
import { maskSecret, type AuthType, type CustomServerForm, type IntegrationConfig } from '../../lib/mcp'

// ── Props ────────────────────────────────────────────────────────────

type ConnectionsTabProps = {
  integrations: IntegrationConfig[]
  onChange: (integrations: IntegrationConfig[]) => void
}

// ── OAuth connector types (from backend) ─────────────────────────────

type ConnectorMeta = {
  id: string
  name: string
  description: string
  icon: string
  services: string[]
  scopes_summary: string
  category: string
  connected: boolean
  configured: boolean
  status: string
  account_email: string | null
  account_name: string | null
  account_avatar: string | null
  connected_at: string | null
}

type ActionMeta = {
  id: string
  name: string
  description: string
  parameters: Record<string, string>
  category: string
}

// ── Platform icons (hosted) ──────────────────────────────────────────

// Bot integration icons (token-based)
const PLATFORM_ICONS: Record<string, string> = {
  telegram: 'https://upload.wikimedia.org/wikipedia/commons/8/82/Telegram_logo.svg',
  discord: 'https://cdn.prod.website-files.com/6257adef93867e50d84d30e2/636e0a69f118df70ad7828d4_icon_clyde_blurple_RGB.svg',
  slack: 'https://a.slack-edge.com/80588/marketing/img/icons/icon_slack_hash_colored.png',
}

// OAuth connector icons — override backend-provided icon to ensure correct logos always display
const CONNECTOR_ICONS: Record<string, string> = {
  google: 'https://www.gstatic.com/images/branding/googleg/1x/googleg_standard_color_128dp.png',
  github: 'https://github.githubassets.com/images/modules/logos_page/GitHub-Mark.png',
  slack: 'https://a.slack-edge.com/80588/marketing/img/icons/icon_slack_hash_colored.png',
  notion: 'https://upload.wikimedia.org/wikipedia/commons/4/45/Notion_app_logo.png',
  linear: 'https://avatars.githubusercontent.com/u/26504447?s=128&v=4',
}

// ── Main Component ───────────────────────────────────────────────────

export function ConnectionsTab({ integrations, onChange }: ConnectionsTabProps) {
  // — OAuth state
  const [connectors, setConnectors] = useState<ConnectorMeta[]>([])
  const [oauthLoading, setOauthLoading] = useState(true)
  const [oauthBusyId, setOauthBusyId] = useState<string | null>(null)
  const [oauthExpandedId, setOauthExpandedId] = useState<string | null>(null)
  const [oauthActions, setOauthActions] = useState<Record<string, ActionMeta[]>>({})

  // — Credential setup form state
  const [credFormId, setCredFormId] = useState<string | null>(null)
  const [credForm, setCredForm] = useState<{ client_id: string; client_secret: string }>({ client_id: '', client_secret: '' })
  const [credSaving, setCredSaving] = useState(false)
  const [credError, setCredError] = useState<string | null>(null)

  // — Bot-token state
  const [botExpandedId, setBotExpandedId] = useState<string | null>(null)
  const [botBusyId, setBotBusyId] = useState<string | null>(null)
  const [botErrors, setBotErrors] = useState<Record<string, string | null>>({})

  // — Custom MCP
  const [showCustom, setShowCustom] = useState(false)
  const [customForm, setCustomForm] = useState<CustomServerForm>({ serverName: '', serverUrl: '', authType: 'none', apiKey: '' })

  // — Global
  const [globalError, setGlobalError] = useState<string | null>(null)

  // Filter: only bot-token integrations (Telegram, Discord, Slack-as-bot)
  const botIntegrations = integrations.filter((i) => ['telegram', 'discord', 'slack'].includes(i.id))
  // Filter: built-in tool integrations (web search, filesystem, code exec)
  const builtInIntegrations = integrations.filter((i) => i.builtIn)

  // ── OAuth connector callback params ────────────────────────────────
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const connected = params.get('connector_connected')
    const connError = params.get('connector_error')
    if (connected || connError) {
      if (connError) setGlobalError(`Connection failed: ${connError}`)
      const url = new URL(window.location.href)
      url.searchParams.delete('connector_connected')
      url.searchParams.delete('connector_error')
      url.searchParams.delete('settings')
      window.history.replaceState({}, '', url.toString())
    }
  }, [])

  // ── Fetch OAuth connectors ─────────────────────────────────────────
  const fetchConnectors = useCallback(async () => {
    try {
      const resp = await fetch(apiUrl('/api/connectors'), { credentials: 'include' })
      const data = await resp.json()
      if (data.ok) setConnectors(data.connectors)
    } catch {
      /* silent */
    } finally {
      setOauthLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchConnectors()
  }, [fetchConnectors])

  // ── OAuth handlers ─────────────────────────────────────────────────
  const handleOAuthConnect = async (connectorId: string) => {
    setOauthBusyId(connectorId)
    setGlobalError(null)
    try {
      const resp = await fetch(apiUrl(`/api/connectors/${connectorId}/authorize`), { credentials: 'include' })
      const data = await resp.json()
      if (data.ok && data.authorize_url) {
        window.location.href = data.authorize_url
      } else {
        setGlobalError(data.detail || 'Failed to start authorization')
      }
    } catch {
      setGlobalError('Failed to start authorization')
    } finally {
      setOauthBusyId(null)
    }
  }

  const handleOAuthDisconnect = async (connectorId: string) => {
    setOauthBusyId(connectorId)
    setGlobalError(null)
    try {
      const resp = await fetch(apiUrl(`/api/connectors/${connectorId}/disconnect`), { method: 'POST', credentials: 'include' })
      const data = await resp.json()
      if (data.ok) await fetchConnectors()
      else setGlobalError(data.detail || 'Failed to disconnect')
    } catch {
      setGlobalError('Failed to disconnect')
    } finally {
      setOauthBusyId(null)
    }
  }

  const loadActions = async (connectorId: string) => {
    if (oauthActions[connectorId]) return
    try {
      const resp = await fetch(apiUrl(`/api/connectors/${connectorId}/actions`), { credentials: 'include' })
      const data = await resp.json()
      if (data.ok) setOauthActions((prev) => ({ ...prev, [connectorId]: data.actions }))
    } catch {
      /* silent */
    }
  }

  const toggleOAuthExpand = (id: string) => {
    const next = oauthExpandedId === id ? null : id
    setOauthExpandedId(next)
    if (next) loadActions(id)
  }

  // ── Credential setup handlers ──────────────────────────────────────
  const openCredForm = (connectorId: string) => {
    setCredFormId(connectorId)
    setCredForm({ client_id: '', client_secret: '' })
    setCredError(null)
  }

  const closeCredForm = () => {
    setCredFormId(null)
    setCredError(null)
  }

  const handleSaveCredentials = async (connectorId: string) => {
    if (!credForm.client_id.trim() || !credForm.client_secret.trim()) {
      setCredError('Both Client ID and Client Secret are required.')
      return
    }
    setCredSaving(true)
    setCredError(null)
    try {
      const resp = await fetch(apiUrl(`/api/connectors/${connectorId}/credentials`), {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ client_id: credForm.client_id.trim(), client_secret: credForm.client_secret.trim() }),
      })
      const data = await resp.json()
      if (data.ok) {
        closeCredForm()
        await fetchConnectors()
      } else {
        setCredError(data.detail || 'Failed to save credentials.')
      }
    } catch {
      setCredError('Network error. Please try again.')
    } finally {
      setCredSaving(false)
    }
  }

  // ── Bot-token handlers ─────────────────────────────────────────────
  const updateIntegration = (id: string, patch: Partial<IntegrationConfig>) => {
    onChange(integrations.map((i) => (i.id === id ? { ...i, ...patch } : i)))
  }

  const setBotError = (id: string, msg: string | null) => {
    setBotErrors((prev) => ({ ...prev, [id]: msg }))
  }

  const postJson = async (path: string, payload: Record<string, unknown>) => {
    const response = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : 'Request failed')
    return data
  }

  const connectBot = async (integration: IntegrationConfig) => {
    const settings = integration.settings ?? {}
    let payload: Record<string, string> = {}
    let endpoint = ''

    if (integration.id === 'telegram') {
      if (!settings.bot_token) { setBotError(integration.id, 'Bot token is required.'); return }
      payload = { bot_token: settings.bot_token, delivery_mode: settings.delivery_mode ?? 'polling', webhook_url: settings.webhook_url ?? '', webhook_secret: settings.webhook_secret ?? '' }
      endpoint = `/api/integrations/telegram/register/${integration.id}`
    } else if (integration.id === 'slack') {
      if (!settings.bot_token && !settings.oauth_token) { setBotError(integration.id, 'Bot token or OAuth token is required.'); return }
      payload = { bot_token: settings.bot_token ?? '', oauth_token: settings.oauth_token ?? '', workspace: settings.workspace ?? '' }
      endpoint = `/api/integrations/slack/register/${integration.id}`
    } else if (integration.id === 'discord') {
      if (!settings.bot_token) { setBotError(integration.id, 'Bot token is required.'); return }
      payload = { bot_token: settings.bot_token, guild_id: settings.guild_id ?? '' }
      endpoint = `/api/integrations/discord/register/${integration.id}`
    }

    setBotBusyId(integration.id)
    setBotError(integration.id, null)
    try {
      const data = await postJson(endpoint, payload)
      const connected = Boolean(data?.connection?.connected)
      updateIntegration(integration.id, { status: connected ? 'connected' : 'error', enabled: connected })
      if (!connected) setBotError(integration.id, 'Connection failed.')
    } catch (err) {
      updateIntegration(integration.id, { status: 'error' })
      setBotError(integration.id, err instanceof Error ? err.message : 'Connection failed.')
    } finally {
      setBotBusyId(null)
    }
  }

  const testBot = async (integration: IntegrationConfig) => {
    setBotBusyId(integration.id)
    setBotError(integration.id, null)
    try {
      const data = await postJson(`/api/integrations/${integration.id}/${integration.id}/test`, {})
      const ok = Boolean(data?.ok)
      updateIntegration(integration.id, { status: ok ? 'connected' : 'error' })
      if (!ok) setBotError(integration.id, `${integration.name} test failed.`)
    } catch (err) {
      updateIntegration(integration.id, { status: 'error' })
      setBotError(integration.id, err instanceof Error ? err.message : 'Test failed.')
    } finally {
      setBotBusyId(null)
    }
  }

  const disconnectBot = (id: string) => {
    updateIntegration(id, { enabled: false, status: 'disabled', settings: {} })
    setBotError(id, null)
    setBotExpandedId(null)
  }

  // ── Custom MCP ─────────────────────────────────────────────────────
  const addCustom = () => {
    if (!customForm.serverName || !customForm.serverUrl) return
    const next: IntegrationConfig = {
      id: crypto.randomUUID(),
      name: customForm.serverName,
      icon: 'custom',
      description: `Custom MCP server at ${customForm.serverUrl}`,
      enabled: false,
      status: 'disabled',
      authType: customForm.authType,
      serverUrl: customForm.serverUrl,
      apiKeyMasked: maskSecret(customForm.apiKey),
      tools: ['custom_tool'],
    }
    onChange([...integrations, next])
    setCustomForm({ serverName: '', serverUrl: '', authType: 'none', apiKey: '' })
    setShowCustom(false)
  }

  // ── Render ─────────────────────────────────────────────────────────
  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h3 className="text-lg font-semibold text-white">Connections</h3>
        <p className="mt-1 text-sm text-zinc-400">
          Connect your accounts and platforms. OAuth apps use secure authorization, bot integrations use token entry.
        </p>
      </div>

      {/* Global error */}
      {globalError && (
        <div className="rounded-lg border border-red-800/50 bg-red-900/20 px-4 py-3 text-sm text-red-300">
          {globalError}
          <button type="button" onClick={() => setGlobalError(null)} className="ml-2 text-red-400 hover:text-red-200">Dismiss</button>
        </div>
      )}

      {/* ─── OAuth Apps ─────────────────────────────────────────── */}
      <section>
        <div className="mb-3 flex items-center gap-2">
          <h4 className="text-sm font-semibold text-zinc-300">OAuth Apps</h4>
          <span className="rounded-full bg-zinc-800 px-2 py-0.5 text-[10px] text-zinc-500">Secure redirect</span>
        </div>

        {oauthLoading ? (
          <div className="flex items-center justify-center py-8">
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
          </div>
        ) : connectors.length === 0 ? (
          <p className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 text-center text-xs text-zinc-500">No OAuth connectors configured on the backend.</p>
        ) : (
          <div className="grid gap-3">
            {connectors.map((c) => {
              const isConn = c.connected && c.status === 'active'
              const busy = oauthBusyId === c.id
              const expanded = oauthExpandedId === c.id
              const acts = oauthActions[c.id] || []

              return (
                <div key={c.id} className="rounded-xl border border-zinc-800 bg-zinc-900/50 transition-colors hover:border-zinc-700">
                  {/* Card header */}
                  <div className="flex items-center gap-4 p-4">
                    <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-zinc-800">
                      <img src={CONNECTOR_ICONS[c.id] || c.icon} alt={c.name} className="h-6 w-6 rounded object-contain" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-white">{c.name}</span>
                        {isConn && <StatusDot color="emerald" label="Connected" />}
                        {c.status === 'expired' && <StatusDot color="amber" label="Expired" />}
                      </div>
                      <p className="mt-0.5 text-xs text-zinc-400">{c.description}</p>
                      {isConn && c.account_email && (
                        <div className="mt-1 flex items-center gap-1.5">
                          {c.account_avatar && <img src={c.account_avatar} alt="" className="h-4 w-4 rounded-full" />}
                          <span className="text-[11px] text-zinc-500">{c.account_name || c.account_email}</span>
                        </div>
                      )}
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      {isConn && (
                        <button type="button" onClick={() => toggleOAuthExpand(c.id)} className="rounded-lg border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-800">
                          {expanded ? 'Hide' : 'Actions'}
                        </button>
                      )}
                      {isConn ? (
                        <button type="button" onClick={() => handleOAuthDisconnect(c.id)} disabled={busy} className="rounded-lg border border-red-800/50 bg-red-900/20 px-3 py-1.5 text-xs text-red-300 hover:bg-red-900/40 disabled:opacity-50">
                          {busy ? 'Disconnecting...' : 'Disconnect'}
                        </button>
                      ) : c.configured ? (
                        <button type="button" onClick={() => handleOAuthConnect(c.id)} disabled={busy} className="rounded-lg bg-blue-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-blue-500 disabled:opacity-50">
                          {busy ? 'Connecting...' : 'Connect'}
                        </button>
                      ) : (
                        <button type="button" onClick={() => openCredForm(c.id)} className="rounded-lg bg-zinc-700 px-4 py-1.5 text-xs font-medium text-white hover:bg-zinc-600" title="Enter OAuth app credentials to enable this connector">
                          Setup
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Services row */}
                  <div className="border-t border-zinc-800/50 px-4 py-2">
                    <div className="flex flex-wrap gap-1.5">
                      {c.services.map((s) => (
                        <span key={s} className="rounded-full bg-zinc-800 px-2.5 py-0.5 text-[10px] font-medium text-zinc-400">{s}</span>
                      ))}
                    </div>
                  </div>

                  {/* Credential setup form (shown when not configured) */}
                  {credFormId === c.id && (
                    <div className="border-t border-zinc-800 px-4 py-3">
                      <div className="mb-2 flex items-center justify-between">
                        <h5 className="text-xs font-semibold uppercase tracking-wider text-zinc-400">OAuth App Credentials</h5>
                        <button type="button" onClick={closeCredForm} className="text-xs text-zinc-500 hover:text-zinc-300">✕ Cancel</button>
                      </div>
                      <p className="mb-3 text-[11px] text-zinc-500">
                        Enter the Client ID and Client Secret from your OAuth app (e.g. from Google Cloud Console, GitHub OAuth Apps).
                      </p>
                      <div className="grid gap-2">
                        <div>
                          <label className="mb-1 block text-[10px] font-medium uppercase tracking-wider text-zinc-500">Client ID</label>
                          <input
                            type="text"
                            value={credForm.client_id}
                            onChange={(e) => setCredForm((f) => ({ ...f, client_id: e.target.value }))}
                            placeholder="e.g. 123456789-abc.apps.googleusercontent.com"
                            className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-xs text-white placeholder-zinc-600 focus:border-blue-500 focus:outline-none"
                            autoComplete="off"
                          />
                        </div>
                        <div>
                          <label className="mb-1 block text-[10px] font-medium uppercase tracking-wider text-zinc-500">Client Secret</label>
                          <input
                            type="password"
                            value={credForm.client_secret}
                            onChange={(e) => setCredForm((f) => ({ ...f, client_secret: e.target.value }))}
                            placeholder="Your client secret"
                            className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-xs text-white placeholder-zinc-600 focus:border-blue-500 focus:outline-none"
                            autoComplete="new-password"
                          />
                        </div>
                        {credError && <p className="text-[11px] text-red-400">{credError}</p>}
                        <button
                          type="button"
                          onClick={() => handleSaveCredentials(c.id)}
                          disabled={credSaving}
                          className="mt-1 rounded-lg bg-blue-600 px-4 py-2 text-xs font-medium text-white hover:bg-blue-500 disabled:opacity-50"
                        >
                          {credSaving ? 'Saving…' : 'Save Credentials'}
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Expanded actions */}
                  {expanded && (
                    <div className="border-t border-zinc-800 px-4 py-3">
                      <h5 className="mb-2 text-xs font-semibold uppercase tracking-wider text-zinc-500">Available Actions</h5>
                      {acts.length === 0 ? (
                        <div className="flex items-center gap-2 text-xs text-zinc-500">
                          <div className="h-3 w-3 animate-spin rounded-full border border-zinc-600 border-t-zinc-400" />Loading...
                        </div>
                      ) : (
                        <div className="grid gap-1.5">
                          {acts.map((a) => (
                            <div key={a.id} className="flex items-start gap-3 rounded-lg bg-zinc-800/50 px-3 py-2">
                              <span className="mt-0.5 rounded bg-zinc-700 px-1.5 py-0.5 text-[9px] font-mono text-zinc-400">{a.category}</span>
                              <div className="min-w-0 flex-1">
                                <span className="text-xs font-medium text-zinc-200">{a.name}</span>
                                <p className="text-[11px] text-zinc-500">{a.description}</p>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </section>

      {/* ─── Bot Integrations ───────────────────────────────────── */}
      <section>
        <div className="mb-3 flex items-center gap-2">
          <h4 className="text-sm font-semibold text-zinc-300">Bot Integrations</h4>
          <span className="rounded-full bg-zinc-800 px-2 py-0.5 text-[10px] text-zinc-500">Token-based</span>
        </div>
        <div className="grid gap-3">
          {botIntegrations.map((integration) => {
            const isBusy = botBusyId === integration.id
            const expanded = botExpandedId === integration.id
            const icon = PLATFORM_ICONS[integration.id]
            const isConn = integration.status === 'connected' && integration.enabled

            return (
              <div key={integration.id} className="rounded-xl border border-zinc-800 bg-zinc-900/50 transition-colors hover:border-zinc-700">
                <div className="flex items-center gap-4 p-4">
                  <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-zinc-800">
                    {icon ? (
                      <img src={icon} alt={integration.name} className="h-6 w-6 object-contain" />
                    ) : (
                      <span className="text-lg">{integration.name.charAt(0)}</span>
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-white">{integration.name}</span>
                      {isConn && <StatusDot color="emerald" label="Connected" />}
                      {integration.status === 'error' && <StatusDot color="red" label="Error" />}
                    </div>
                    <p className="mt-0.5 text-xs text-zinc-400">{integration.description}</p>
                    <p className="mt-0.5 text-[11px] text-zinc-500">Tools: {integration.tools.join(', ')}</p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setBotExpandedId(expanded ? null : integration.id)}
                      className="rounded-lg border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-800"
                    >
                      {expanded ? 'Close' : 'Configure'}
                    </button>
                    {isConn ? (
                      <button type="button" onClick={() => disconnectBot(integration.id)} className="rounded-lg border border-red-800/50 bg-red-900/20 px-3 py-1.5 text-xs text-red-300 hover:bg-red-900/40">
                        Disconnect
                      </button>
                    ) : (
                      <button type="button" onClick={() => { setBotExpandedId(integration.id) }} className="rounded-lg bg-blue-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-blue-500">
                        Set Up
                      </button>
                    )}
                  </div>
                </div>

                {/* Config forms */}
                {expanded && (
                  <div className="border-t border-zinc-800 px-4 py-3">
                    {integration.id === 'telegram' && (
                      <TelegramForm integration={integration} busy={isBusy} onUpdate={(p) => updateIntegration(integration.id, p)} onConnect={() => connectBot(integration)} onTest={() => testBot(integration)} />
                    )}
                    {integration.id === 'slack' && (
                      <SlackBotForm integration={integration} busy={isBusy} onUpdate={(p) => updateIntegration(integration.id, p)} onConnect={() => connectBot(integration)} onTest={() => testBot(integration)} />
                    )}
                    {integration.id === 'discord' && (
                      <DiscordForm integration={integration} busy={isBusy} onUpdate={(p) => updateIntegration(integration.id, p)} onConnect={() => connectBot(integration)} onTest={() => testBot(integration)} />
                    )}
                  </div>
                )}

                {/* Error */}
                {botErrors[integration.id] && (
                  <div className="border-t border-red-900/30 px-4 py-2">
                    <p className="text-xs text-red-300">{botErrors[integration.id]}</p>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </section>

      {/* ─── Built-in Tools ─────────────────────────────────────── */}
      {builtInIntegrations.length > 0 && (
        <section>
          <div className="mb-3 flex items-center gap-2">
            <h4 className="text-sm font-semibold text-zinc-300">Built-in Tools</h4>
            <span className="rounded-full bg-zinc-800 px-2 py-0.5 text-[10px] text-zinc-500">No setup required</span>
          </div>
          <div className="grid gap-2">
            {builtInIntegrations.map((integration) => (
              <div key={integration.id} className="flex items-center justify-between rounded-xl border border-zinc-800 bg-zinc-900/50 px-4 py-3">
                <div>
                  <span className="text-sm font-medium text-white">{integration.name}</span>
                  <p className="text-xs text-zinc-400">{integration.description}</p>
                </div>
                <button
                  type="button"
                  onClick={() => updateIntegration(integration.id, { enabled: !integration.enabled, status: integration.enabled ? 'disabled' : 'connected' })}
                  className={`relative h-6 w-11 rounded-full transition-colors ${integration.enabled ? 'bg-blue-600' : 'bg-zinc-700'}`}
                >
                  <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${integration.enabled ? 'left-[22px]' : 'left-0.5'}`} />
                </button>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ─── Custom MCP Server ──────────────────────────────────── */}
      <section>
        <button
          type="button"
          onClick={() => setShowCustom(!showCustom)}
          className="flex items-center gap-2 text-sm text-blue-400 hover:text-blue-300"
        >
          <span className="text-lg leading-none">{showCustom ? '−' : '+'}</span>
          Add Custom MCP Server
        </button>
        {showCustom && (
          <div className="mt-3 rounded-xl border border-zinc-800 bg-zinc-900/50 p-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <input placeholder="Server name" value={customForm.serverName} onChange={(e) => setCustomForm((p) => ({ ...p, serverName: e.target.value }))} className="rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-white placeholder-zinc-500 focus:border-blue-500 focus:outline-none" />
              <input placeholder="Server URL (http://localhost:3000/mcp)" value={customForm.serverUrl} onChange={(e) => setCustomForm((p) => ({ ...p, serverUrl: e.target.value }))} className="rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-white placeholder-zinc-500 focus:border-blue-500 focus:outline-none" />
              <label htmlFor="custom-mcp-auth" className="sr-only">Auth type</label>
              <select id="custom-mcp-auth" value={customForm.authType} onChange={(e) => setCustomForm((p) => ({ ...p, authType: e.target.value as AuthType }))} className="rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none">
                <option value="none">No Auth</option>
                <option value="api_key">API Key</option>
                <option value="oauth">OAuth</option>
              </select>
              <input placeholder="API Key (optional)" value={customForm.apiKey} onChange={(e) => setCustomForm((p) => ({ ...p, apiKey: e.target.value }))} className="rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-white placeholder-zinc-500 focus:border-blue-500 focus:outline-none" />
            </div>
            <div className="mt-3 flex gap-2">
              <button type="button" onClick={addCustom} disabled={!customForm.serverName || !customForm.serverUrl} className="rounded-lg bg-blue-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-blue-500 disabled:opacity-50">Save</button>
              <button type="button" onClick={() => setShowCustom(false)} className="rounded-lg border border-zinc-700 px-4 py-1.5 text-xs text-zinc-300 hover:bg-zinc-800">Cancel</button>
            </div>
          </div>
        )}
      </section>
    </div>
  )
}

// ── Status Dot ───────────────────────────────────────────────────────

function StatusDot({ color, label }: { color: 'emerald' | 'amber' | 'red'; label: string }) {
  const colors = {
    emerald: { bg: 'bg-emerald-900/30', text: 'text-emerald-400', dot: 'bg-emerald-400' },
    amber: { bg: 'bg-amber-900/30', text: 'text-amber-400', dot: 'bg-amber-400' },
    red: { bg: 'bg-red-900/30', text: 'text-red-400', dot: 'bg-red-400' },
  }
  const c = colors[color]
  return (
    <span className={`inline-flex items-center gap-1 rounded-full ${c.bg} px-2 py-0.5 text-[10px] font-medium ${c.text}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${c.dot}`} />
      {label}
    </span>
  )
}

// ── Bot Config Forms ─────────────────────────────────────────────────

type BotFormProps = {
  integration: IntegrationConfig
  busy: boolean
  onUpdate: (patch: Partial<IntegrationConfig>) => void
  onConnect: () => void
  onTest: () => void
}

const inputCls = 'w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-white placeholder-zinc-500 focus:border-blue-500 focus:outline-none'

function TelegramForm({ integration, busy, onUpdate, onConnect, onTest }: BotFormProps) {
  const s = integration.settings ?? {}
  const set = (key: string, val: string) => onUpdate({ settings: { ...s, [key]: val } })
  return (
    <div className="grid gap-2.5">
      <p className="text-xs text-zinc-400">Get a bot token from <a href="https://t.me/BotFather" target="_blank" rel="noreferrer" className="text-blue-400 hover:underline">@BotFather</a> on Telegram.</p>
      <input placeholder="Bot token" value={s.bot_token ?? ''} onChange={(e) => set('bot_token', e.target.value)} className={inputCls} />
      <label htmlFor="tg-delivery" className="sr-only">Delivery mode</label>
      <select id="tg-delivery" value={s.delivery_mode ?? 'polling'} onChange={(e) => set('delivery_mode', e.target.value)} className={inputCls}>
        <option value="polling">Polling</option>
        <option value="webhook">Webhook</option>
      </select>
      {s.delivery_mode === 'webhook' && (
        <>
          <input placeholder="Webhook URL" value={s.webhook_url ?? ''} onChange={(e) => set('webhook_url', e.target.value)} className={inputCls} />
          <input placeholder="Webhook secret (optional)" value={s.webhook_secret ?? ''} onChange={(e) => set('webhook_secret', e.target.value)} className={inputCls} />
        </>
      )}
      <div className="flex gap-2">
        <button type="button" onClick={onConnect} disabled={busy} className="rounded-lg bg-blue-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-blue-500 disabled:opacity-50">
          {busy ? 'Connecting...' : 'Save & Connect'}
        </button>
        <button type="button" onClick={onTest} disabled={busy} className="rounded-lg border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-800 disabled:opacity-50">
          Test
        </button>
      </div>
    </div>
  )
}

function SlackBotForm({ integration, busy, onUpdate, onConnect, onTest }: BotFormProps) {
  const s = integration.settings ?? {}
  const set = (key: string, val: string) => onUpdate({ settings: { ...s, [key]: val } })
  return (
    <div className="grid gap-2.5">
      <p className="text-xs text-zinc-400">Enter a Slack bot token to run Aegis as a bot in your workspace. For personal account access, use the OAuth connector above.</p>
      <input placeholder="Bot token (xoxb-...)" value={s.bot_token ?? ''} onChange={(e) => set('bot_token', e.target.value)} className={inputCls} />
      <input placeholder="Workspace name (optional)" value={s.workspace ?? ''} onChange={(e) => set('workspace', e.target.value)} className={inputCls} />
      <div className="flex gap-2">
        <button type="button" onClick={onConnect} disabled={busy} className="rounded-lg bg-blue-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-blue-500 disabled:opacity-50">
          {busy ? 'Connecting...' : 'Save & Connect'}
        </button>
        <button type="button" onClick={onTest} disabled={busy} className="rounded-lg border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-800 disabled:opacity-50">
          Test
        </button>
      </div>
    </div>
  )
}

function DiscordForm({ integration, busy, onUpdate, onConnect, onTest }: BotFormProps) {
  const s = integration.settings ?? {}
  const set = (key: string, val: string) => onUpdate({ settings: { ...s, [key]: val } })
  return (
    <div className="grid gap-2.5">
      <p className="text-xs text-zinc-400">Create a bot at the <a href="https://discord.com/developers/applications" target="_blank" rel="noreferrer" className="text-blue-400 hover:underline">Discord Developer Portal</a>, then paste the bot token.</p>
      <input placeholder="Bot token" value={s.bot_token ?? ''} onChange={(e) => set('bot_token', e.target.value)} className={inputCls} />
      <input placeholder="Guild ID (optional)" value={s.guild_id ?? ''} onChange={(e) => set('guild_id', e.target.value)} className={inputCls} />
      <div className="flex gap-2">
        <button type="button" onClick={onConnect} disabled={busy} className="rounded-lg bg-blue-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-blue-500 disabled:opacity-50">
          {busy ? 'Connecting...' : 'Save & Connect'}
        </button>
        <button type="button" onClick={onTest} disabled={busy} className="rounded-lg border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-800 disabled:opacity-50">
          Test
        </button>
      </div>
    </div>
  )
}
