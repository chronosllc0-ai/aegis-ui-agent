import { useCallback, useEffect, useMemo, useState } from 'react'
import { DEMO_WORKFLOW_TEMPLATES } from '../lib/demoData'
import { DEFAULT_INTEGRATIONS, type IntegrationConfig } from '../lib/mcp'

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
  model: string
  autoScreenshot: boolean
  verboseLogging: boolean
  confirmDestructiveActions: boolean
  integrations: IntegrationConfig[]
  workflowTemplates: WorkflowTemplate[]
}

const STORAGE_KEY = 'aegis.settings.v3'

const DEFAULT_SETTINGS: AppSettings = {
  displayName: 'Aegis User',
  avatarUrl: '',
  email: 'user@example.com',
  theme: 'dark',
  systemInstruction: 'You are Aegis. Be helpful, concise, and safe when taking actions.',
  personalityPreset: 'Professional',
  temperature: 0.7,
  model: 'gemini-2.5-pro',
  autoScreenshot: true,
  verboseLogging: false,
  confirmDestructiveActions: true,
  integrations: DEFAULT_INTEGRATIONS,
  workflowTemplates: import.meta.env.DEV ? DEMO_WORKFLOW_TEMPLATES : [],
}

function loadInitialSettings(): AppSettings {
  const raw = localStorage.getItem(STORAGE_KEY)
  if (!raw) return DEFAULT_SETTINGS
  try {
    const parsed = JSON.parse(raw) as Partial<AppSettings>
    return { ...DEFAULT_SETTINGS, ...parsed }
  } catch {
    localStorage.removeItem(STORAGE_KEY)
    return DEFAULT_SETTINGS
  }
}

export function useSettings() {
  const [settings, setSettings] = useState<AppSettings>(loadInitialSettings)
export function useSettings() {
  const [settings, setSettings] = useState<AppSettings>(DEFAULT_SETTINGS)

  useEffect(() => {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return
    try {
      const parsed = JSON.parse(raw) as Partial<AppSettings>
      setSettings((prev) => ({ ...prev, ...parsed }))
    } catch {
      localStorage.removeItem(STORAGE_KEY)
    }
  }, [])

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
