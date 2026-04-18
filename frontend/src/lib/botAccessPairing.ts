import { apiUrl } from './api'

export type ChatPolicyMode = 'allow_all' | 'allowlist' | 'deny_all'

export type PairingPendingRequest = {
  request_id: string
  external_user_id: string
  external_username: string | null
  chat_type: string | null
  external_channel_id: string | null
  created_at: string | null
  code_expires_at: string | null
}

export type IntegrationPolicy = {
  pairing_required: boolean
  allow_direct_messages: boolean
  allow_group_messages: boolean
  reject_message: string
  updated_at: string | null
}

export type BotAccessConfig = {
  allow_from: string[]
  dm_allow_from: string[]
  group_allow_from: string[]
  dm_policy_mode: ChatPolicyMode
  group_policy_mode: ChatPolicyMode
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(path), { credentials: 'include', ...init })
  const data = await response.json().catch(() => ({}))
  if (!response.ok || data?.ok === false) {
    throw new Error(typeof data?.detail === 'string' ? data.detail : 'Request failed')
  }
  return data as T
}

export async function getPendingPairing(platform: string, integrationId: string): Promise<PairingPendingRequest[]> {
  const data = await requestJson<{ pending?: PairingPendingRequest[] }>(`/api/integrations/${platform}/${integrationId}/pairing/pending`)
  return Array.isArray(data.pending) ? data.pending : []
}

export async function approvePairing(platform: string, integrationId: string, requestId: string): Promise<void> {
  await requestJson(`/api/integrations/${platform}/${integrationId}/pairing/${requestId}/approve`, { method: 'POST' })
}

export async function denyPairing(platform: string, integrationId: string, requestId: string): Promise<void> {
  await requestJson(`/api/integrations/${platform}/${integrationId}/pairing/${requestId}/deny`, { method: 'POST' })
}

export async function getIntegrationPolicy(platform: string, integrationId: string): Promise<IntegrationPolicy> {
  const data = await requestJson<{ policy?: IntegrationPolicy }>(`/api/integrations/${platform}/${integrationId}/policy`)
  return {
    pairing_required: Boolean(data.policy?.pairing_required),
    allow_direct_messages: Boolean(data.policy?.allow_direct_messages),
    allow_group_messages: Boolean(data.policy?.allow_group_messages),
    reject_message: data.policy?.reject_message ?? 'Access denied for this bot integration.',
    updated_at: data.policy?.updated_at ?? null,
  }
}

export async function updateIntegrationPolicy(platform: string, integrationId: string, payload: Partial<IntegrationPolicy>): Promise<void> {
  await requestJson(`/api/integrations/${platform}/${integrationId}/policy`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function getBotAccessConfig(platform: string, integrationId: string): Promise<BotAccessConfig> {
  const data = await requestJson<{ config?: Record<string, unknown> }>(`/api/integrations/${platform}/config/${integrationId}`)
  const cfg = data.config ?? {}
  const normalizeList = (value: unknown): string[] => Array.isArray(value) ? value.map((item) => String(item)).filter(Boolean) : []
  const normalizeMode = (value: unknown): ChatPolicyMode => (value === 'allowlist' || value === 'deny_all' ? value : 'allow_all')
  return {
    allow_from: normalizeList(cfg.allow_from),
    dm_allow_from: normalizeList(cfg.dm_allow_from),
    group_allow_from: normalizeList(cfg.group_allow_from),
    dm_policy_mode: normalizeMode(cfg.dm_policy_mode),
    group_policy_mode: normalizeMode(cfg.group_policy_mode),
  }
}

export async function saveBotAccessConfig(platform: string, integrationId: string, patch: Partial<BotAccessConfig>): Promise<void> {
  const current = await getBotAccessConfig(platform, integrationId)
  await requestJson(`/api/integrations/${platform}/config/${integrationId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...current, ...patch }),
  })
}
