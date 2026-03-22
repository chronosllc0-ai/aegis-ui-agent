import { useMemo } from 'react'

type Criterion = {
  label: string
  met: boolean
}

export function usePasswordCriteria(password: string): { criteria: Criterion[]; score: number; label: string } {
  return useMemo(() => {
    const criteria: Criterion[] = [
      { label: 'At least 8 characters', met: password.length >= 8 },
      { label: 'Uppercase letter (A-Z)', met: /[A-Z]/.test(password) },
      { label: 'Lowercase letter (a-z)', met: /[a-z]/.test(password) },
      { label: 'Number (0-9)', met: /[0-9]/.test(password) },
      { label: 'Special character (!@#$…)', met: /[^A-Za-z0-9]/.test(password) },
    ]
    const score = criteria.filter((c) => c.met).length
    const label =
      score <= 1 ? 'Very weak' : score === 2 ? 'Weak' : score === 3 ? 'Fair' : score === 4 ? 'Strong' : 'Very strong'
    return { criteria, score, label }
  }, [password])
}

const BAR_COLORS = ['bg-red-500', 'bg-red-500', 'bg-orange-500', 'bg-yellow-500', 'bg-emerald-500', 'bg-emerald-400']
const LABEL_COLORS = [
  'text-zinc-500',
  'text-red-400',
  'text-orange-400',
  'text-yellow-400',
  'text-emerald-400',
  'text-emerald-300',
]

export function PasswordStrength({ password }: { password: string }) {
  const { criteria, score, label } = usePasswordCriteria(password)

  if (!password) return null

  return (
    <div className='mt-1 space-y-2'>
      {/* strength bar */}
      <div className='flex items-center gap-2'>
        <div className='flex flex-1 gap-1'>
          {Array.from({ length: 5 }).map((_, i) => (
            <div
              key={i}
              className={`h-1 flex-1 rounded-full transition-colors ${i < score ? BAR_COLORS[score] : 'bg-white/8'}`}
            />
          ))}
        </div>
        <span className={`text-xs font-medium ${LABEL_COLORS[score]}`}>{label}</span>
      </div>

      {/* criteria list */}
      <ul className='grid gap-1 text-xs'>
        {criteria.map((c) => (
          <li key={c.label} className='flex items-center gap-2'>
            {c.met ? (
              <svg
                viewBox='0 0 16 16'
                className='h-3.5 w-3.5 shrink-0 text-emerald-400'
                fill='none'
                stroke='currentColor'
                strokeWidth='2'
                strokeLinecap='round'
                strokeLinejoin='round'
              >
                <path d='m3 8 3.5 3.5L13 5' />
              </svg>
            ) : (
              <svg viewBox='0 0 16 16' className='h-3.5 w-3.5 shrink-0 text-zinc-600' fill='currentColor'>
                <circle cx='8' cy='8' r='3' />
              </svg>
            )}
            <span className={c.met ? 'text-zinc-300' : 'text-zinc-500'}>{c.label}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
