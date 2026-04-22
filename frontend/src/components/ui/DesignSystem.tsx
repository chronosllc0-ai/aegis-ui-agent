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
    <section className='space-y-1.5'>
      <button
        type='button'
        onClick={() => setCollapsed((prev) => !prev)}
        className='flex min-h-9 w-full items-center justify-between rounded-lg px-1.5 text-left md:cursor-default focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ds-border-accent)] focus-visible:ring-offset-1 focus-visible:ring-offset-[var(--ds-surface-1)]'
        aria-expanded={!collapsed}
      >
        <p className='text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--ds-text-muted)]'>{title}</p>
        <span className='md:hidden'>{Icons.chevronDown({ className: `h-3.5 w-3.5 text-[var(--ds-text-muted)] transition-transform ${collapsed ? '-rotate-90' : 'rotate-0'}` })}</span>
      </button>
      <div className={`${collapsed ? 'hidden md:block' : 'block'} space-y-0.5`}>{children}</div>
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
      className={`group flex min-h-10 w-full items-center gap-2 rounded-lg px-2.5 text-left text-sm font-semibold transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ds-border-accent)] focus-visible:ring-offset-1 focus-visible:ring-offset-[var(--ds-surface-1)] ${
        active
          ? 'bg-[var(--ds-accent-soft)] text-[var(--ds-text-primary)] shadow-[var(--ds-shadow-soft)]'
          : 'text-[var(--ds-text-primary)]/90 hover:bg-[var(--ds-surface-3)]/45'
      }`}
    >
      <span className={`${active ? 'text-[var(--ds-text-primary)]' : 'text-[var(--ds-text-secondary)] group-hover:text-[var(--ds-text-primary)]'}`}>{icon}</span>
      <span className={`leading-5 ${active ? 'shadow-[inset_0_-1px_0_var(--ds-border-accent)]' : 'shadow-[inset_0_-1px_0_transparent] group-hover:shadow-[inset_0_-1px_0_var(--ds-border-subtle)]'}`}>
        {label}
      </span>
    </button>
  )
}

type PanelCardProps = {
  children: ReactNode
  className?: string
}

export function PanelCard({ children, className = '' }: PanelCardProps) {
  return <section className={`rounded-[var(--ds-layout-card-radius)] border border-[var(--ds-border-subtle)] bg-[var(--ds-surface-2)] p-3 sm:p-4 ${className}`}>{children}</section>
}

type PageSectionProps = {
  children: ReactNode
  className?: string
}

export function PageSection({ children, className = '' }: PageSectionProps) {
  return <section className={`page-section ${className}`}>{children}</section>
}

type SurfaceCardProps = {
  children: ReactNode
  className?: string
}

export function SurfaceCard({ children, className = '' }: SurfaceCardProps) {
  return <div className={`rounded-[var(--ds-layout-card-radius)] border border-[var(--ds-border-subtle)] bg-[var(--ds-surface-2)] p-4 sm:p-5 ${className}`}>{children}</div>
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
    <header className={`sticky top-1 z-20 min-h-[var(--ds-layout-header-height)] rounded-[var(--ds-layout-card-radius)] border border-[var(--ds-border-subtle)] bg-[var(--ds-surface-1)]/95 px-3 py-2 backdrop-blur ${className}`}>
      <div className='flex min-h-11 items-center justify-between gap-2'>
        <div className='min-w-0'>{left}</div>
        {right && <div className='shrink-0'>{right}</div>}
      </div>
    </header>
  )
}
