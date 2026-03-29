import { useCallback, useEffect, useMemo, useState } from 'react'
import { DEFAULT_INTEGRATIONS, normalizeIntegrationConfig, type IntegrationConfig } from '../lib/mcp'

export type ThemePreference = 'dark' | 'light' | 'system'

export type WorkflowTemplate = {
  id: string
  name: string
  instruction: string
  stepCount: number
  lastRunAt: string
}

export type AppSettings = {
  displayName: string
  avatarUrl: string
  email: string
  theme: ThemePreference
  systemInstruction: string
  personalityPreset: string
  temperature: number
  provider: string
  model: string
  autoScreenshot: boolean
  verboseLogging: boolean
  confirmDestructiveActions: boolean
  integrations: IntegrationConfig[]
  workflowTemplates: WorkflowTemplate[]
}

const STORAGE_KEY = 'aegis.settings.v4'

const DEFAULT_SETTINGS: AppSettings = {
  displayName: 'Aegis User',
  avatarUrl: '',
  email: 'user@example.com',
  theme: 'dark',
  systemInstruction: 'You are Aegis. Be helpful, concise, and safe when taking actions.',
  personalityPreset: 'Professional',
  temperature: 0.7,
  provider: 'chronos',
  model: 'nvidia/llama-3.3-nemotron-super-49b-v1:free',
  autoScreenshot: true,
  verboseLogging: false,
  confirmDestructiveActions: true,
  integrations: DEFAULT_INTEGRATIONS,
  workflowTemplates: [],
}

// Providers that require a user-supplied BYOK key to work
const BYOK_PROVIDERS = new Set(['openai', 'anthropic', 'google', 'xai', 'openrouter'])

function loadInitialSettings(): AppSettings {
  const raw = localStorage.getItem(STORAGE_KEY)
  if (!raw) return DEFAULT_SETTINGS
  try {
    const parsed = JSON.parse(raw) as Partial<AppSettings>
    const merged = { ...DEFAULT_SETTINGS, ...parsed }

    // Migration: if the stored provider is a BYOK provider but no key is stored for it,
    // reset to Chronos Gateway so the agent actually works out of the box.
    if (merged.provider && BYOK_PROVIDERS.has(merged.provider)) {
      const byokKey = localStorage.getItem(`aegis.byok.${merged.provider}`)
      if (!byokKey) {
        merged.provider = DEFAULT_SETTINGS.provider
        merged.model = DEFAULT_SETTINGS.model
      }
    }

    return {
      ...merged,
      integrations: Array.isArray(merged.integrations)
        ? merged.integrations.map((integration) => normalizeIntegrationConfig(integration))
        : DEFAULT_SETTINGS.integrations,
    }
  } catch {
    localStorage.removeItem(STORAGE_KEY)
    return DEFAULT_SETTINGS
  }
}

export function useSettings() {
  const [settings, setSettings] = useState<AppSettings>(loadInitialSettings)

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings))
  }, [settings])

  useEffect(() => {
    if (settings.theme === 'dark') {
      document.documentElement.classList.add('dark')
      return
    }
    if (settings.theme === 'light') {
      document.documentElement.classList.remove('dark')
      return
    }
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
    document.documentElement.classList.toggle('dark', prefersDark)
  }, [settings.theme])

  const patchSettings = useCallback((partial: Partial<AppSettings>) => {
    setSettings((prev) => ({ ...prev, ...partial }))
  }, [])

  const syncToFirestore = useCallback(async () => {
    await Promise.resolve()
  }, [])

  const wsConfig = useMemo(
    () => ({
      provider: settings.provider,
      model: settings.model,
      system_instruction: settings.systemInstruction,
      temperature: settings.temperature,
      behavior: {
        auto_screenshot: settings.autoScreenshot,
        verbose_logging: settings.verboseLogging,
        confirm_destructive_actions: settings.confirmDestructiveActions,
      },
      integrations: settings.integrations.filter((integration) => integration.enabled),
    }),
    [settings],
  )

  return { settings, patchSettings, setSettings, syncToFirestore, wsConfig }
}
