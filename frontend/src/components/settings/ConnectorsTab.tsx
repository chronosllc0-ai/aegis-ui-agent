import { useCallback, useEffect, useState } from 'react'
import { apiUrl } from '../../lib/api'

// ── Types ────────────────────────────────────────────────────────────

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

// ── Component ────────────────────────────────────────────────────────

export function ConnectorsTab() {
  const [connectors, setConnectors] = useState<ConnectorMeta[]>([])
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [actions, setActions] = useState<Record<string, ActionMeta[]>>({})
  const [error, setError] = useState<string | null>(null)

  // Check URL params for connector callback status
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const connected = params.get('connector_connected')
    const connError = params.get('connector_error')
    if (connected) {
      // Clean up URL
      const url = new URL(window.location.href)
      url.searchParams.delete('connector_connected')
      url.searchParams.delete('settings')
      window.history.replaceState({}, '', url.toString())
    }
    if (connError) {
      const detail = params.get('connector_error_detail')
      const label = connError === 'credentials_not_configured'
        ? 'Connector credentials not configured — add Client ID & Secret in Settings → Connections.'
        : detail
          ? `Connection failed: ${connError} — ${decodeURIComponent(detail)}`
          : `Connection failed: ${connError}`
      setError(label)
      const url = new URL(window.location.href)
      url.searchParams.delete('connector_error')
      url.searchParams.delete('connector_error_detail')
      url.searchParams.delete('settings')
      window.history.replaceState({}, '', url.toString())
    }
  }, [])

  const fetchConnectors = useCallback(async () => {
    try {
      const resp = await fetch(apiUrl('/api/connectors'), { credentials: 'include' })
      const data = await resp.json()
      if (data.ok) {
        setConnectors(data.connectors)
      }
    } catch {
      setError('Failed to load connectors')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchConnectors()
  }, [fetchConnectors])

  const handleConnect = async (connectorId: string) => {
    setBusyId(connectorId)
    setError(null)
    try {
      const resp = await fetch(apiUrl(`/api/connectors/${connectorId}/authorize`), { credentials: 'include' })
      const data = await resp.json()
      if (data.ok && data.authorize_url) {
        // Redirect to OAuth provider
        window.location.href = data.authorize_url
      } else {
        setError(data.detail || 'Failed to start authorization')
      }
    } catch {
      setError('Failed to start authorization')
    } finally {
      setBusyId(null)
    }
  }

  const handleDisconnect = async (connectorId: string) => {
    setBusyId(connectorId)
    setError(null)
    try {
      const resp = await fetch(apiUrl(`/api/connectors/${connectorId}/disconnect`), {
        method: 'POST',
        credentials: 'include',
      })
      const data = await resp.json()
      if (data.ok) {
        await fetchConnectors()
      } else {
        setError(data.detail || 'Failed to disconnect')
      }
    } catch {
      setError('Failed to disconnect')
    } finally {
      setBusyId(null)
    }
  }

  const loadActions = async (connectorId: string) => {
    if (actions[connectorId]) return
    try {
      const resp = await fetch(apiUrl(`/api/connectors/${connectorId}/actions`), { credentials: 'include' })
      const data = await resp.json()
      if (data.ok) {
        setActions((prev) => ({ ...prev, [connectorId]: data.actions }))
      }
    } catch {
      // Silently fail
    }
  }

  const toggleExpand = (connectorId: string) => {
    const next = expandedId === connectorId ? null : connectorId
    setExpandedId(next)
    if (next) loadActions(connectorId)
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-white">Connected Apps</h3>
        <p className="mt-1 text-sm text-zinc-400">
          Connect your accounts so Aegis can read and write to your tools. All tokens are encrypted at rest.
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-red-800/50 bg-red-900/20 px-4 py-3 text-sm text-red-300">
          {error}
          <button type="button" onClick={() => setError(null)} className="ml-2 text-red-400 hover:text-red-200">
            Dismiss
          </button>
        </div>
      )}

      <div className="grid gap-4">
        {connectors.map((c) => (
          <ConnectorCard
            key={c.id}
            connector={c}
            expanded={expandedId === c.id}
            busy={busyId === c.id}
            actions={actions[c.id] || []}
            onConnect={() => handleConnect(c.id)}
            onDisconnect={() => handleDisconnect(c.id)}
            onToggle={() => toggleExpand(c.id)}
          />
        ))}
      </div>

      {connectors.length === 0 && (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-8 text-center text-sm text-zinc-500">
          No connectors available. Check your backend configuration.
        </div>
      )}
    </div>
  )
}

// ── Connector Card ───────────────────────────────────────────────────

type ConnectorCardProps = {
  connector: ConnectorMeta
  expanded: boolean
  busy: boolean
  actions: ActionMeta[]
  onConnect: () => void
  onDisconnect: () => void
  onToggle: () => void
}

function ConnectorCard({ connector, expanded, busy, actions, onConnect, onDisconnect, onToggle }: ConnectorCardProps) {
  const c = connector
  const isConnected = c.connected && c.status === 'active'

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 transition-colors hover:border-zinc-700">
      {/* Header */}
      <div className="flex items-center gap-4 p-4">
        {/* Icon */}
        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-zinc-800">
          <img src={c.icon} alt={c.name} className="h-7 w-7 rounded object-contain" />
        </div>

        {/* Info */}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-white">{c.name}</span>
            <StatusBadge connected={isConnected} status={c.status} />
          </div>
          <p className="mt-0.5 text-xs text-zinc-400">{c.description}</p>
          {isConnected && c.account_email && (
            <div className="mt-1 flex items-center gap-2">
              {c.account_avatar && (
                <img src={c.account_avatar} alt="" className="h-4 w-4 rounded-full" />
              )}
              <span className="text-xs text-zinc-500">{c.account_name || c.account_email}</span>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex shrink-0 items-center gap-2">
          {isConnected && (
            <button
              type="button"
              onClick={onToggle}
              className="rounded-lg border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 transition-colors hover:bg-zinc-800"
            >
              {expanded ? 'Hide' : 'Actions'}
            </button>
          )}

          {isConnected ? (
            <button
              type="button"
              onClick={onDisconnect}
              disabled={busy}
              className="rounded-lg border border-red-800/50 bg-red-900/20 px-3 py-1.5 text-xs text-red-300 transition-colors hover:bg-red-900/40 disabled:opacity-50"
            >
              {busy ? 'Disconnecting...' : 'Disconnect'}
            </button>
          ) : (
            <button
              type="button"
              onClick={onConnect}
              disabled={busy || !c.configured}
              className="rounded-lg bg-blue-600 px-4 py-1.5 text-xs font-medium text-white transition-colors hover:bg-blue-500 disabled:opacity-50"
              title={!c.configured ? 'Not configured — admin needs to set OAuth credentials' : undefined}
            >
              {busy ? (
                <span className="flex items-center gap-1.5">
                  <span className="h-3 w-3 animate-spin rounded-full border border-white/30 border-t-white" />
                  Connecting...
                </span>
              ) : (
                'Connect'
              )}
            </button>
          )}
        </div>
      </div>

      {/* Services chips */}
      <div className="border-t border-zinc-800/50 px-4 py-2">
        <div className="flex flex-wrap gap-1.5">
          {c.services.map((s) => (
            <span key={s} className="rounded-full bg-zinc-800 px-2.5 py-0.5 text-[10px] font-medium text-zinc-400">
              {s}
            </span>
          ))}
        </div>
      </div>

      {/* Expanded: actions list */}
      {expanded && (
        <div className="border-t border-zinc-800 px-4 py-3">
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-zinc-500">Available Actions</h4>
          {actions.length === 0 ? (
            <div className="flex items-center gap-2 text-xs text-zinc-500">
              <div className="h-3 w-3 animate-spin rounded-full border border-zinc-600 border-t-zinc-400" />
              Loading actions...
            </div>
          ) : (
            <div className="grid gap-1.5">
              {actions.map((a) => (
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
}

// ── Status Badge ─────────────────────────────────────────────────────

function StatusBadge({ connected, status }: { connected: boolean; status: string }) {
  if (connected) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-900/30 px-2 py-0.5 text-[10px] font-medium text-emerald-400">
        <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
        Connected
      </span>
    )
  }
  if (status === 'expired') {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-amber-900/30 px-2 py-0.5 text-[10px] font-medium text-amber-400">
        <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
        Expired
      </span>
    )
  }
  return null
}
