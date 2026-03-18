import { useContext } from 'react'
import { SettingsContext, type SettingsContextValue } from './settings-context'
import { SettingsContext, type SettingsContextValue } from './SettingsContextValue'

export function useSettingsContext(): SettingsContextValue {
  const context = useContext(SettingsContext)
  if (!context) throw new Error('useSettingsContext must be used inside SettingsProvider')
  return context
}
