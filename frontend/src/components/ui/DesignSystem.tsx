import { type ReactNode, useState } from 'react'
import { Icons } from '../icons'

type SidebarSectionProps = {
  title: string
  children: ReactNode
  defaultCollapsed?: boolean
}

export function SidebarSection({ title, children, defaultCollapsed = false }: SidebarSectionProps) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed)

  return (
    <section className='rounded-2xl border border-[var(--ds-border-subtle)] bg-[var(--ds-surface-2)]/65 p-2'>
      <button
        type='button'
        onClick={() => setCollapsed((prev) => !prev)}
        className='flex min-h-11 w-full items-center justify-between rounded-xl px-2 text-left md:cursor-default'
        aria-expanded={!collapsed}
      >
        <p className='text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--ds-text-muted)]'>{title}</p>
        <span className='md:hidden'>{Icons.chevronDown({ className: `h-3.5 w-3.5 text-[var(--ds-text-muted)] transition-transform ${collapsed ? '-rotate-90' : 'rotate-0'}` })}</span>
      </button>
      <div className={`${collapsed ? 'hidden md:block' : 'block'} space-y-1 px-1 pb-1`}>{children}</div>
    </section>
  )
}

type NavItemProps = {
  icon: ReactNode
  label: string
  active?: boolean
  onClick: () => void
}

export function NavItem({ icon, label, active = false, onClick }: NavItemProps) {
  return (
    <button
      type='button'
      onClick={onClick}
      className={`flex min-h-11 w-full items-center gap-2 rounded-xl border px-3 text-left text-sm transition-colors cursor-pointer ${
        active
          ? 'border-[var(--ds-border-accent)] bg-[var(--ds-accent-soft)] text-[var(--ds-text-primary)] shadow-[var(--ds-shadow-soft)]'
          : 'border-[var(--ds-border-subtle)] bg-[var(--ds-surface-3)] text-[var(--ds-text-secondary)] hover:border-[var(--ds-border-strong)] hover:bg-[var(--ds-surface-4)]'
      }`}
    >
      <span className='text-[var(--ds-text-muted)]'>{icon}</span>
      <span>{label}</span>
    </button>
  )
}

type PanelCardProps = {
  children: ReactNode
  className?: string
}

export function PanelCard({ children, className = '' }: PanelCardProps) {
  return <section className={`rounded-2xl border border-[var(--ds-border-subtle)] bg-[var(--ds-surface-2)] p-3 sm:p-4 ${className}`}>{children}</section>
}

type StatusBadgeProps = {
  label: string
  tone?: 'default' | 'success' | 'warning' | 'danger' | 'info'
}

const toneClass: Record<NonNullable<StatusBadgeProps['tone']>, string> = {
  default: 'border-[var(--ds-border-subtle)] bg-[var(--ds-surface-3)] text-[var(--ds-text-muted)]',
  success: 'border-emerald-500/35 bg-emerald-500/12 text-emerald-200',
  warning: 'border-amber-500/35 bg-amber-500/12 text-amber-200',
  danger: 'border-rose-500/35 bg-rose-500/12 text-rose-200',
  info: 'border-sky-500/35 bg-sky-500/12 text-sky-200',
}

export function StatusBadge({ label, tone = 'default' }: StatusBadgeProps) {
  return <span className={`rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ${toneClass[tone]}`}>{label}</span>
}

type HeaderBarProps = {
  left: ReactNode
  right?: ReactNode
  className?: string
}

export function HeaderBar({ left, right, className = '' }: HeaderBarProps) {
  return (
    <header className={`sticky top-1 z-20 rounded-2xl border border-[var(--ds-border-subtle)] bg-[var(--ds-surface-1)]/95 px-3 py-2 backdrop-blur ${className}`}>
      <div className='flex min-h-11 items-center justify-between gap-2'>
        <div className='min-w-0'>{left}</div>
        {right && <div className='shrink-0'>{right}</div>}
      </div>
    </header>
  )
}
