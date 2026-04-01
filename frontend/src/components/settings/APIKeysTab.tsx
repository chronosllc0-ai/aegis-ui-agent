import { useEffect, useState } from 'react'
import { Icons } from '../icons'
import { useToast } from '../../hooks/useToast'
import { useNotifications } from '../../context/NotificationContext'
import { PROVIDERS, renderProviderIcon } from '../../lib/models'
import { apiUrl } from '../../lib/api'

type StoredKey = {
  provider: string
  key_hint: string
  has_key: boolean
}

export function APIKeysTab() {
  const [keys, setKeys] = useState<StoredKey[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState<string | null>(null)
  const [inputs, setInputs] = useState<Record<string, string>>({})
  const [message, setMessage] = useState<{ type: 'ok' | 'err'; text: string } | null>(null)
  const toast = useToast()
  const { addNotification } = useNotifications()

  const loadKeys = async () => {
    setLoading(true)
    try {
      const res = await fetch(apiUrl('/api/keys'), { credentials: 'include' })
      const data = await res.json().catch(() => ({}))
      if (data?.keys) setKeys(data.keys)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadKeys()
  }, [])

  const saveKey = async (providerId: string) => {
    const key = inputs[providerId]?.trim()
    if (!key) return
    setSaving(providerId)
    setMessage(null)
    try {
      const res = await fetch(apiUrl('/api/keys'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ provider: providerId, api_key: key }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data?.detail ?? 'Failed to save key')
      toast.success('API key saved', `${providerId} key connected successfully.`)
      addNotification({ type: 'success', title: `${providerId} API key connected`, message: 'Key saved and encrypted. Charges go to your provider account.', source: 'api_key' })
      setMessage({ type: 'ok', text: `${providerId} key saved.` })
      setInputs((prev) => ({ ...prev, [providerId]: '' }))
      await loadKeys()
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : 'Failed to save key'
      toast.error('Failed to save key', errMsg)
      addNotification({ type: 'error', title: 'API key save failed', message: errMsg, source: 'api_key' })
      setMessage({ type: 'err', text: errMsg })
    } finally {
      setSaving(null)
    }
  }

  const deleteKey = async (providerId: string) => {
    setSaving(providerId)
    setMessage(null)
    try {
      const res = await fetch(apiUrl(`/api/keys/${providerId}`), {
        method: 'DELETE',
        credentials: 'include',
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data?.detail ?? 'Failed to delete key')
      }
      toast.success('API key removed', `${providerId} key disconnected.`)
      setMessage({ type: 'ok', text: `${providerId} key removed.` })
      await loadKeys()
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : 'Failed to delete key'
      toast.error('Failed to remove key', errMsg)
      setMessage({ type: 'err', text: errMsg })
    } finally {
      setSaving(null)
    }
  }

  const storedMap = Object.fromEntries(keys.map((k) => [k.provider, k]))

  const byokProviders = PROVIDERS.filter((p) => !p.gatewayOnly)

  return (
    <div className='space-y-6'>
      <div className='rounded-xl border border-violet-500/30 bg-violet-500/5 p-3 text-xs text-violet-200'>
        <span className='font-semibold'>Chronos Gateway</span> uses platform API keys - no key needed. Select <em>Chronos Gateway</em> in the Agent tab and start immediately. Credits are deducted per request.
      </div>

      <div>
        <h3 className='text-sm font-semibold'>Bring Your Own Key (BYOK)</h3>
        <p className='mt-1 text-xs text-zinc-400'>
          Add your own API keys to unlock any provider. Keys are encrypted at rest and never shared.
          If no key is set for a provider the platform default is used (when available).
        </p>
      </div>

      {message && (
        <p className={`text-xs ${message.type === 'ok' ? 'text-emerald-300' : 'text-red-300'}`}>
          {message.text}
        </p>
      )}

      {loading && (
        <p className='text-xs text-zinc-500'>Loading saved API keys...</p>
      )}

      <div className='space-y-4'>
        {byokProviders.map((provider) => {
          const stored = storedMap[provider.id]
          const isBusy = saving === provider.id
          return (
            <div key={provider.id} className='rounded-xl border border-[#2a2a2a] bg-[#111] p-4'>
              <div className='flex min-w-0 items-center justify-between gap-2'>
                <div className='flex min-w-0 items-center gap-2'>
                  <span className='text-base text-zinc-100 shrink-0'>{renderProviderIcon(provider, 'h-5 w-5')}</span>
                  <span className='text-sm font-medium truncate'>{provider.displayName}</span>
                </div>
                {stored ? (
                  <span className='inline-flex shrink-0 items-center gap-1 text-xs text-emerald-300'>
                    <span className='h-2 w-2 rounded-full bg-emerald-400' />
                    <span className='truncate max-w-[120px]'>Connected / {stored.key_hint}</span>
                  </span>
                ) : (
                  <span className='shrink-0 text-xs text-zinc-500'>No key</span>
                )}
              </div>
              <div className='mt-3 flex min-w-0 gap-2'>
                <input
                  type='password'
                  placeholder={`${provider.displayName} API key${provider.keyPrefix ? ` (${provider.keyPrefix}...)` : ''}`}
                  value={inputs[provider.id] ?? ''}
                  onChange={(e) => setInputs((prev) => ({ ...prev, [provider.id]: e.target.value }))}
                  className='min-w-0 flex-1 rounded-lg border border-[#2a2a2a] bg-[#0f0f0f] px-3 py-2 text-sm'
                />
                <button
                  type='button'
                  onClick={() => saveKey(provider.id)}
                  disabled={isBusy || !inputs[provider.id]?.trim()}
                  className='rounded-lg bg-blue-600 px-3 py-2 text-xs font-medium hover:bg-blue-500 disabled:opacity-50'
                >
                  {stored ? 'Update' : 'Save'}
                </button>
                {stored && (
                  <button
                    type='button'
                    onClick={() => deleteKey(provider.id)}
                    disabled={isBusy}
                    className='rounded-lg border border-red-500/40 px-3 py-2 text-xs text-red-300 hover:bg-red-500/10 disabled:opacity-50'
                  >
                    Remove
                  </button>
                )}
              </div>
              <p className='mt-2 text-[11px] text-zinc-500'>
                {provider.models.length} models: {provider.models.slice(0, 3).map((m) => m.label).join(', ')}
                {provider.models.length > 3 ? `, +${provider.models.length - 3} more` : ''}
              </p>
            </div>
          )
        })}
      </div>

      <div className='rounded-xl border border-blue-500/20 bg-blue-500/5 p-4 text-xs text-zinc-300'>
        <p className='inline-flex items-center gap-2 font-medium text-blue-200'>
          {Icons.lock({ className: 'h-3.5 w-3.5' })}
          <span>How BYOK works</span>
        </p>
        <ul className='mt-2 list-inside list-disc space-y-1 text-zinc-400'>
          <li>Keys are encrypted with AES-256 before storage - we never see your plaintext key.</li>
          <li>Each request to an LLM uses <em>your</em> key, billed directly to your provider account.</li>
          <li>You can remove a key anytime; Aegis falls back to the platform default or disables the provider.</li>
          <li>No key data is ever logged or transmitted to third parties.</li>
        </ul>
      </div>
    </div>
  )
}
