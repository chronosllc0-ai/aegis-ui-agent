import { useCallback, useEffect, useState } from 'react'

import {
  approvePairing,
  denyPairing,
  getBotAccessConfig,
  getIntegrationPolicy,
  getPendingPairing,
  saveBotAccessConfig,
  type BotAccessConfig,
  type ChatPolicyMode,
  type IntegrationPolicy,
  type PairingPendingRequest,
  updateIntegrationPolicy,
} from '../lib/botAccessPairing'

type UseBotAccessPairingState = {
  loading: boolean
  error: string | null
  saving: boolean
  pending: PairingPendingRequest[]
  policy: IntegrationPolicy | null
  accessConfig: BotAccessConfig | null
}

const EMPTY_LIST: PairingPendingRequest[] = []

export function useBotAccessPairing(platform: string, integrationId: string) {
  const [state, setState] = useState<UseBotAccessPairingState>({
    loading: true,
    error: null,
    saving: false,
    pending: EMPTY_LIST,
    policy: null,
    accessConfig: null,
  })

  const refresh = useCallback(async () => {
    setState((prev) => ({ ...prev, loading: true, error: null }))
    try {
      const [pending, policy, accessConfig] = await Promise.all([
        getPendingPairing(platform, integrationId),
        getIntegrationPolicy(platform, integrationId),
        getBotAccessConfig(platform, integrationId),
      ])
      setState((prev) => ({ ...prev, loading: false, pending, policy, accessConfig }))
    } catch (error) {
      setState((prev) => ({
        ...prev,
        loading: false,
        error: error instanceof Error ? error.message : 'Failed to load access & pairing settings.',
      }))
    }
  }, [platform, integrationId])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const decide = useCallback(async (requestId: string, action: 'approve' | 'deny') => {
    setState((prev) => ({ ...prev, saving: true, error: null }))
    try {
      if (action === 'approve') await approvePairing(platform, integrationId, requestId)
      else await denyPairing(platform, integrationId, requestId)
      await refresh()
    } catch (error) {
      setState((prev) => ({ ...prev, saving: false, error: error instanceof Error ? error.message : 'Failed to update request.' }))
      return
    }
    setState((prev) => ({ ...prev, saving: false }))
  }, [platform, integrationId, refresh])

  const updatePairingRequired = useCallback(async (pairingRequired: boolean) => {
    setState((prev) => ({ ...prev, saving: true, error: null }))
    try {
      await updateIntegrationPolicy(platform, integrationId, { pairing_required: pairingRequired })
      setState((prev) => ({
        ...prev,
        saving: false,
        policy: prev.policy ? { ...prev.policy, pairing_required: pairingRequired } : prev.policy,
      }))
    } catch (error) {
      setState((prev) => ({ ...prev, saving: false, error: error instanceof Error ? error.message : 'Failed to save pairing policy.' }))
    }
  }, [platform, integrationId])

  const updateChatPolicy = useCallback(async (chatType: 'dm' | 'group', mode: ChatPolicyMode, allowlist: string[]) => {
    const trimmedAllowlist = allowlist.map((item) => item.trim()).filter(Boolean)
    const allowMessages = mode !== 'deny_all'
    const policyPatch: Partial<IntegrationPolicy> = chatType === 'dm'
      ? { allow_direct_messages: allowMessages }
      : { allow_group_messages: allowMessages }

    const configPatch: Partial<BotAccessConfig> = chatType === 'dm'
      ? { dm_policy_mode: mode, dm_allow_from: trimmedAllowlist }
      : { group_policy_mode: mode, group_allow_from: trimmedAllowlist }

    setState((prev) => ({ ...prev, saving: true, error: null }))
    try {
      await Promise.all([
        updateIntegrationPolicy(platform, integrationId, policyPatch),
        saveBotAccessConfig(platform, integrationId, configPatch),
      ])
      setState((prev) => ({
        ...prev,
        saving: false,
        policy: prev.policy
          ? {
            ...prev.policy,
            ...(chatType === 'dm' ? { allow_direct_messages: allowMessages } : { allow_group_messages: allowMessages }),
          }
          : prev.policy,
        accessConfig: prev.accessConfig
          ? {
            ...prev.accessConfig,
            ...(chatType === 'dm'
              ? { dm_policy_mode: mode, dm_allow_from: trimmedAllowlist }
              : { group_policy_mode: mode, group_allow_from: trimmedAllowlist }),
          }
          : prev.accessConfig,
      }))
    } catch (error) {
      setState((prev) => ({ ...prev, saving: false, error: error instanceof Error ? error.message : 'Failed to save chat policy.' }))
    }
  }, [platform, integrationId])

  return {
    ...state,
    refresh,
    decide,
    updatePairingRequired,
    updateChatPolicy,
  }
}
