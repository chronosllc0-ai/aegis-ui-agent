import type { IntegrationConfig } from './mcp'

export type NativeIntegrationResponse = {
  kind: string
  status: string
  config: Record<string, unknown>
  masked_credentials: Record<string, string>
  last_health_check?: string
  last_success_action?: string
  last_error?: string
  tools: Array<{ name: string; description: string }>
}

export type MCPServerResponse = {
  server_id: string
  name: string
  transport: 'streamable_http' | 'sse' | 'stdio'
  connected: boolean
  tool_count: number
  last_test_at?: string
  config_summary?: { url?: string; command?: string }
}

const USER_ID = 'demo-user'

export async function fetchIntegrations(): Promise<{ native: NativeIntegrationResponse[]; mcp: MCPServerResponse[] }> {
  const response = await fetch(`/api/integrations?user_id=${USER_ID}`)
  if (!response.ok) {
    throw new Error('Failed to load integrations')
  }
  const data = await response.json()
  return { native: data.native_integrations ?? [], mcp: data.mcp_servers ?? [] }
}

export async function connectNative(kind: string, config: Record<string, unknown>, secrets: Record<string, string>): Promise<void> {
  const response = await fetch(`/api/integrations/${kind}/connect`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: USER_ID, config, secrets }),
  })
  if (!response.ok) throw new Error((await response.json()).detail ?? 'Connect failed')
}

export async function testNative(kind: string): Promise<void> {
  const response = await fetch(`/api/integrations/${kind}/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: USER_ID }),
  })
  if (!response.ok) throw new Error((await response.json()).detail ?? 'Test failed')
}

export async function executeNative(kind: string, toolName: string, params: Record<string, unknown>): Promise<unknown> {
  const response = await fetch(`/api/integrations/${kind}/execute`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: USER_ID, tool_name: toolName, params }),
  })
  const data = await response.json()
  if (!response.ok) throw new Error(data.detail ?? 'Execute failed')
  return data
}

export async function disconnectNative(kind: string): Promise<void> {
  const response = await fetch(`/api/integrations/${kind}?user_id=${USER_ID}`, { method: 'DELETE' })
  if (!response.ok) throw new Error('Disconnect failed')
}

export async function addMcpServer(payload: {
  name: string
  transport: 'streamable_http' | 'sse' | 'stdio'
  config: Record<string, unknown>
  secrets?: Record<string, string>
}): Promise<void> {
  const response = await fetch('/api/mcp/servers', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: USER_ID, ...payload }),
  })
  const data = await response.json()
  if (!response.ok) throw new Error(data.detail ?? 'Failed to add MCP server')
}

export async function testMcpServer(serverId: string): Promise<void> {
  const response = await fetch(`/api/mcp/servers/${serverId}/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: USER_ID }),
  })
  const data = await response.json()
  if (!response.ok) throw new Error(data.detail ?? 'MCP test failed')
}

export async function deleteMcpServer(serverId: string): Promise<void> {
  const response = await fetch(`/api/mcp/servers/${serverId}?user_id=${USER_ID}`, { method: 'DELETE' })
  if (!response.ok) throw new Error('MCP delete failed')
}

export function mergeNativeIntoSettings(existing: IntegrationConfig[], native: NativeIntegrationResponse[]): IntegrationConfig[] {
  const existingById = new Map(existing.map((item) => [item.id, item]))
  return native.map((item) => {
    const base = existingById.get(item.kind)
    return {
      id: item.kind,
      name: base?.name ?? item.kind,
      icon: base?.icon ?? item.kind,
      description: base?.description ?? 'Native integration',
      enabled: item.status === 'connected',
      status: item.status === 'connected' ? 'connected' : item.status === 'error' ? 'error' : 'disabled',
      builtIn: true,
      authType: base?.authType,
      settings: Object.fromEntries(Object.entries(item.masked_credentials).map(([k, v]) => [k, v])),
      tools: item.tools.map((tool) => tool.name),
      scopes: base?.scopes,
      lastCheckedAt: item.last_health_check,
      lastUsedAt: item.last_success_action,
    }
  })
}
