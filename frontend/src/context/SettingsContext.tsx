import { createContext, useContext, type ReactNode } from 'react'
import { useSettings } from '../hooks/useSettings'

type SettingsContextValue = ReturnType<typeof useSettings>

const SettingsContext = createContext<SettingsContextValue | null>(null)

export function SettingsProvider({ children }: { children: ReactNode }) {
  const value = useSettings()
  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>
}

export function useSettingsContext(): SettingsContextValue {
  const context = useContext(SettingsContext)
  if (!context) throw new Error('useSettingsContext must be used inside SettingsProvider')
  return context
}
