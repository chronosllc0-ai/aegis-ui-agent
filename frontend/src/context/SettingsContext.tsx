import type { ReactNode } from 'react'
import { useSettings } from '../hooks/useSettings'
import { SettingsContext } from './SettingsContextValue'

export function SettingsProvider({ children }: { children: ReactNode }) {
  const value = useSettings()
  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>
}
