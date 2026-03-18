import { createContext } from 'react'
import type { useSettings } from '../hooks/useSettings'

export type SettingsContextValue = ReturnType<typeof useSettings>

export const SettingsContext = createContext<SettingsContextValue | null>(null)
