import { useState } from 'react'
import { Icons } from './icons'

// Each release entry
type ReleaseEntry = {
  version: string
  date: string
  changes: { type: 'new' | 'fix' | 'improve'; text: string }[]
}

// Add new releases at the top of this array
const RELEASES: ReleaseEntry[] = [
  {
    version: '1.2.1',
    date: 'April 2026',
    changes: [
      { type: 'improve', text: 'Reasoning controls moved to Settings → Agent for supported models, with medium/high/extended/adaptive mode controls' },
      { type: 'improve', text: 'Reasoning is now enabled by default for new settings profiles (default effort: medium)' },
      { type: 'fix', text: 'Sandbox shell executor now runs via non-login shell mode for safer command startup behavior' },
    ],
  },
  {
    version: '1.2.0',
    date: 'March 2026',
    changes: [
      { type: 'new', text: 'Sub-agent orchestration - Aegis can now spawn and coordinate multiple AI sub-agents to tackle complex multi-step tasks in parallel' },
      { type: 'new', text: 'Cross-device chat persistence - conversation history now synced to the server DB and available on any device after login' },
      { type: 'new', text: 'Connector OAuth overhaul - Notion, Google Drive, Slack integrations with robust token refresh and error handling' },
      { type: 'fix', text: 'Notion OAuth invalid_grant - workspace_id/workspace_name now passed correctly in token exchange' },
      { type: 'fix', text: 'Gemini Live voice model updated to gemini-3.1-flash-live-preview' },
      { type: 'improve', text: 'Action log and chat fonts scaled up on desktop for better readability' },
    ],
  },
  {
    version: '1.1.0',
    date: 'March 2026',
    changes: [
      { type: 'new', text: 'Bot slash commands: /run, /steer, /interrupt, /queue, /status, /stream' },
      { type: 'new', text: 'Live screenshot streaming to Telegram/Discord via /stream' },
      { type: 'new', text: 'Bot config panel in Settings → Connections' },
      { type: 'new', text: 'Auto-registers slash commands with Telegram BotFather on connect' },
      { type: 'improve', text: 'Mobile layout: dynamic viewport height, overflow fixes' },
      { type: 'improve', text: 'SEO: meta tags, OG image, robots.txt, sitemap.xml' },
      { type: 'improve', text: 'Steering bar now hidden until agent is actively working' },
      { type: 'fix', text: 'Fixed latent NameError: _extract_session_user_uid and _extract_websocket_user_uid' },
    ],
  },
  {
    version: '1.0.0',
    date: 'March 2026',
    changes: [
      { type: 'new', text: 'xAI (Grok) and OpenRouter added as AI providers' },
      { type: 'new', text: 'Notification bell with credit/quota and disconnect alerts' },
      { type: 'new', text: 'Privacy Policy and Terms of Service pages' },
      { type: 'new', text: 'Admin-only OAuth credential setup in Connections' },
      { type: 'new', text: 'Superadmin auto-seed via SUPERADMIN_EMAIL/PASSWORD env vars' },
      { type: 'new', text: 'Slack Marketplace install endpoint' },
      { type: 'improve', text: 'Password strength indicator and confirm password feedback on signup' },
      { type: 'improve', text: 'Onboarding wizard and product tour for new users' },
      { type: 'improve', text: 'Mobile responsive layout across all pages' },
      { type: 'fix', text: 'OAuth connector icons use reliable CDN sources' },
    ],
  },
]

const TYPE_LABELS = { new: '✦ New', fix: '⬡ Fix', improve: '◈ Improved' }
const TYPE_COLORS = {
  new: 'text-blue-400',
  fix: 'text-emerald-400',
  improve: 'text-purple-400',
}

export function ChangelogModal({ onClose }: { onClose: () => void }) {
  const latest = RELEASES[0]

  return (
    <div className='fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm'>
      <div className='relative w-full max-w-lg rounded-2xl border border-[#2a2a2a] bg-[#0f0f0f] shadow-2xl'>
        {/* Header */}
        <div className='flex items-center justify-between border-b border-[#2a2a2a] px-5 py-4'>
          <div>
            <h2 className='text-base font-semibold text-zinc-100'>What's new in Aegis</h2>
            <p className='mt-0.5 text-xs text-zinc-500'>v{latest.version} · {latest.date}</p>
          </div>
          <button
            type='button'
            onClick={onClose}
            className='rounded-lg border border-[#2a2a2a] p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200'
          >
            {Icons.close({ className: 'h-4 w-4' })}
          </button>
        </div>

        {/* Releases list */}
        <div className='max-h-[60vh] overflow-y-auto divide-y divide-[#1a1a1a]'>
          {RELEASES.map((release) => (
            <div key={release.version} className='px-5 py-4'>
              {RELEASES.indexOf(release) > 0 && (
                <p className='mb-3 text-xs font-medium text-zinc-500'>v{release.version} · {release.date}</p>
              )}
              <ul className='space-y-2'>
                {release.changes.map((change, i) => (
                  <li key={i} className='flex items-start gap-2.5 text-sm'>
                    <span className={`shrink-0 text-[11px] font-medium mt-0.5 ${TYPE_COLORS[change.type]}`}>
                      {TYPE_LABELS[change.type]}
                    </span>
                    <span className='text-zinc-300'>{change.text}</span>
                  </li>
                ))}
              </ul>
              {/* TODO: Add showcase images/videos for this release */}
              <div className='mt-4 rounded-xl border border-dashed border-[#2a2a2a] bg-[#0a0a0a] flex items-center justify-center h-32 text-zinc-600 text-xs'>
                📸 Add screenshots or video for v{release.version} here
              </div>
            </div>
          ))}
        </div>

        {/* Footer */}
        <div className='flex items-center justify-between border-t border-[#2a2a2a] px-5 py-3'>
          <span className='text-xs text-zinc-600'>Aegis v{latest.version}</span>
          <button
            type='button'
            onClick={onClose}
            className='rounded-lg bg-blue-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-blue-500'
          >
            Got it
          </button>
        </div>
      </div>
    </div>
  )
}

export function SubAgentModal({ onClose, onTryNow }: { onClose: () => void; onTryNow: () => void }) {
  return (
    <div className='fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm'>
      <div className='relative w-full max-w-md rounded-2xl border border-[#2a2a2a] bg-[#0f0f0f] shadow-2xl'>
        {/* Header */}
        <div className='flex items-center justify-between border-b border-[#2a2a2a] px-5 py-4'>
          <h2 className='text-base font-semibold text-zinc-100'>🧠 Aegis can now orchestrate sub-agents</h2>
          <button
            type='button'
            onClick={onClose}
            className='rounded-lg border border-[#2a2a2a] p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200'
          >
            {Icons.close({ className: 'h-4 w-4' })}
          </button>
        </div>

        {/* Body */}
        <div className='px-5 py-4'>
          <p className='text-sm text-zinc-300 leading-relaxed'>
            Aegis can now break complex tasks into parallel workstreams, spawning specialized sub-agents for research, coding, browsing, and data analysis - all coordinated in real time.
          </p>

          {/* Video placeholder */}
          <div className='my-4 rounded-xl border border-dashed border-[#2a2a2a] bg-[#0a0a0a] flex items-center justify-center h-40 text-zinc-600 text-xs'>
            ▶ Add demo video here
          </div>

          {/* Capabilities list */}
          <ul className='space-y-2 text-sm text-zinc-300'>
            <li>🔍 Parallel web research across multiple sources</li>
            <li>💻 Code generation + testing in sandboxed environments</li>
            <li>📊 Data aggregation, analysis, and visualization</li>
            <li>🌐 Multi-site browsing and form automation</li>
          </ul>
        </div>

        {/* Footer */}
        <div className='flex flex-col items-center gap-2 border-t border-[#2a2a2a] px-5 py-4'>
          <button
            type='button'
            onClick={onTryNow}
            className='w-full rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-500'
          >
            Try it now →
          </button>
          <button
            type='button'
            onClick={onClose}
            className='text-xs text-zinc-500 hover:text-zinc-300'
          >
            Maybe later
          </button>
        </div>
      </div>
    </div>
  )
}

// Hook to manage changelog visibility
export function useChangelog() {
  const appVersion = (import.meta.env.VITE_APP_VERSION as string | undefined) ?? '1.2.0'
  const storageKey = 'aegis_last_version'
  const lastSeen = typeof window !== 'undefined' ? localStorage.getItem(storageKey) : null
  const [show, setShow] = useState<boolean>(!!appVersion && appVersion !== lastSeen)

  const dismiss = () => {
    localStorage.setItem(storageKey, appVersion)
    setShow(false)
  }

  return { show, dismiss, version: appVersion }
}
