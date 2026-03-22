import { useState } from 'react'

type PasswordInputProps = {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  autoComplete?: string
}

function EyeIcon({ open }: { open: boolean }) {
  if (open) {
    // eye-open
    return (
      <svg
        viewBox='0 0 24 24'
        className='h-4 w-4'
        fill='none'
        stroke='currentColor'
        strokeWidth='1.8'
        strokeLinecap='round'
        strokeLinejoin='round'
      >
        <path d='M1 12s4-8 11-8 11 8 11 8-4 8-11 8S1 12 1 12z' />
        <circle cx='12' cy='12' r='3' />
      </svg>
    )
  }
  // eye-off
  return (
    <svg
      viewBox='0 0 24 24'
      className='h-4 w-4'
      fill='none'
      stroke='currentColor'
      strokeWidth='1.8'
      strokeLinecap='round'
      strokeLinejoin='round'
    >
      <path d='M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94' />
      <path d='M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19' />
      <path d='M14.12 14.12a3 3 0 1 1-4.24-4.24' />
      <line x1='1' y1='1' x2='23' y2='23' />
    </svg>
  )
}

export function PasswordInput({ value, onChange, placeholder = 'Enter your password', autoComplete }: PasswordInputProps) {
  const [visible, setVisible] = useState(false)

  return (
    <div className='relative'>
      <input
        type={visible ? 'text' : 'password'}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        autoComplete={autoComplete}
        className='w-full rounded-2xl border border-white/8 bg-[#090c13] px-4 py-3 pr-11 text-sm text-zinc-100 outline-none transition focus:border-cyan-400/30'
      />
      <button
        type='button'
        tabIndex={-1}
        onClick={() => setVisible((v) => !v)}
        className='absolute right-3 top-1/2 -translate-y-1/2 rounded-lg p-1 text-zinc-500 transition hover:text-zinc-300'
        aria-label={visible ? 'Hide password' : 'Show password'}
      >
        <EyeIcon open={visible} />
      </button>
    </div>
  )
}
