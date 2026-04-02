import { useCallback, useEffect, useMemo, useState } from 'react'
import { DEFAULT_INTEGRATIONS, mergeIntegrationCatalog, type IntegrationConfig } from '../lib/mcp'

export type ThemePreference = 'dark' | 'light' | 'system'

export type ReasoningEffort = 'medium' | 'high' | 'extended' | 'adaptive'

export type WorkflowTemplate = {
  id: string
  name: string
  instruction: string
  stepCount: number
  lastRunAt: string
}

/** Per-tool permission mode.
 *  'auto'    - agent runs this tool without asking (default)
 *  'confirm' - agent sends an approval card before using this tool */
export type ToolPermission = 'auto' | 'confirm'

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
  /** Map of toolId → permission mode. Missing key = 'auto'. */
  toolPermissions: Record<string, ToolPermission>
  /** Set of toolIds the user has explicitly disabled (agent will not call them). */
  disabledTools: string[]
  /** Whether to enable reasoning/thinking tokens for models that support it. */
  enableReasoning: boolean
  /** Reasoning effort level for models that support it (e.g. o3, grok-3-mini). */
  reasoningEffort: ReasoningEffort
}

const STORAGE_KEY = 'aegis.settings.v4'

export const DEFAULT_SYSTEM_INSTRUCTION = 'You are Aegis. Be helpful, concise, and safe. Use only enabled tools, respect connected integrations, ask for approval before destructive actions, and when working with GitHub clone into the session workspace, use a feature branch, verify changes, then commit, push, and open a pull request only when the user asks.'

const DEFAULT_SETTINGS: AppSettings = {
  displayName: 'Aegis User',
  avatarUrl: '',
  email: 'user@example.com',
  theme: 'dark',
  systemInstruction: DEFAULT_SYSTEM_INSTRUCTION,
  personalityPreset: 'Professional',
  temperature: 0.7,
  provider: 'chronos',
  model: 'nvidia/nemotron-3-super-120b-a12b:free',
  autoScreenshot: true,
  verboseLogging: false,
  confirmDestructiveActions: true,
  integrations: DEFAULT_INTEGRATIONS,
  workflowTemplates: [],
  toolPermissions: {},
  disabledTools: [],
  enableReasoning: true,
  reasoningEffort: 'medium',
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
      integrations: mergeIntegrationCatalog(Array.isArray(merged.integrations) ? merged.integrations : undefined),
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
      tool_permissions: settings.toolPermissions,
      disabled_tools: settings.disabledTools,
      enable_reasoning: settings.enableReasoning,
      reasoning_effort: settings.reasoningEffort,
    }),
    [settings],
  )

  return { settings, patchSettings, setSettings, syncToFirestore, wsConfig }
}
