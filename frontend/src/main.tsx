import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
<<<<<<< ours
import App from './App'
import { SettingsProvider } from './context/SettingsContext'
import './index.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <SettingsProvider>
      <App />
    </SettingsProvider>
=======
import './index.css'
import App from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
>>>>>>> theirs
  </StrictMode>,
)
