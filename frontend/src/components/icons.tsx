/* eslint-disable react-refresh/only-export-components */
import type { ReactNode } from 'react'
import type { IconType } from 'react-icons'
import { SiDiscord, SiSlack, SiTelegram } from 'react-icons/si'
import { LuCode, LuFolder, LuGlobe, LuLock, LuPlus } from 'react-icons/lu'

type IconProps = {
  className?: string
}

function Svg({ className, children }: IconProps & { children: ReactNode }) {
  return (
    <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='1.8' strokeLinecap='round' strokeLinejoin='round' className={className ?? 'h-4 w-4'} aria-hidden='true'>
      {children}
    </svg>
  )
}

export const Icons = {
  menu: (p: IconProps) => <Svg {...p}><path d='M4 7h16M4 12h16M4 17h16' /></Svg>,
  search: (p: IconProps) => <Svg {...p}><circle cx='11' cy='11' r='6' /><path d='m20 20-3.5-3.5' /></Svg>,
  plus: (p: IconProps) => <Svg {...p}><path d='M12 5v14M5 12h14' /></Svg>,
  settings: (p: IconProps) => <Svg {...p}><circle cx='12' cy='12' r='3.2' /><path d='M19 12a7 7 0 0 0-.1-1l2-1.6-2-3.5-2.4 1A7 7 0 0 0 14 5L13.7 2h-4l-.3 3a7 7 0 0 0-2.5 1l-2.4-1-2 3.5 2 1.6a7 7 0 0 0 0 2l-2 1.6 2 3.5 2.4-1a7 7 0 0 0 2.5 1l.3 3h4l.3-3a7 7 0 0 0 2.5-1l2.4 1 2-3.5-2-1.6c.1-.3.1-.7.1-1Z' /></Svg>,
  workflows: (p: IconProps) => <Svg {...p}><circle cx='5' cy='6' r='2' /><circle cx='19' cy='6' r='2' /><circle cx='12' cy='18' r='2' /><path d='M7 7.5l3.5 7M17 7.5l-3.5 7' /></Svg>,
  user: (p: IconProps) => <Svg {...p}><circle cx='12' cy='8' r='3.2' /><path d='M5 20c1.8-3.5 4.3-5 7-5s5.2 1.5 7 5' /></Svg>,
  logout: (p: IconProps) => <Svg {...p}><path d='M9 4H5v16h4' /><path d='m13 8 5 4-5 4' /><path d='M18 12H9' /></Svg>,
  back: (p: IconProps) => <Svg {...p}><path d='m15 18-6-6 6-6' /></Svg>,
  chevronRight: (p: IconProps) => <Svg {...p}><path d='m9 18 6-6-6-6' /></Svg>,
  chevronDown: (p: IconProps) => <Svg {...p}><path d='m6 9 6 6 6-6' /></Svg>,
  globe: (p: IconProps) => <Svg {...p}><circle cx='12' cy='12' r='9' /><path d='M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18' /></Svg>,
  copy: (p: IconProps) => <Svg {...p}><rect x='9' y='9' width='11' height='11' rx='2' /><rect x='4' y='4' width='11' height='11' rx='2' /></Svg>,
  save: (p: IconProps) => <Svg {...p}><path d='M5 4h12l2 2v14H5z' /><path d='M8 4v6h8V4M9 20v-6h6v6' /></Svg>,
  play: (p: IconProps) => <Svg {...p}><path d='m9 7 9 5-9 5z' /></Svg>,
  edit: (p: IconProps) => <Svg {...p}><path d='M4 20h4l10-10-4-4L4 16zM12 6l4 4' /></Svg>,
  duplicate: (p: IconProps) => <Svg {...p}><rect x='8' y='8' width='11' height='11' rx='2' /><rect x='5' y='5' width='11' height='11' rx='2' /></Svg>,
  trash: (p: IconProps) => <Svg {...p}><path d='M4 7h16M9 7V5h6v2M8 7l1 12h6l1-12' /></Svg>,
  star: (p: IconProps) => <Svg {...p}><path d='m12 3 2.7 5.5 6 .9-4.3 4.2 1 5.9-5.4-2.8-5.4 2.8 1-5.9L3.3 9.4l6-.9z' /></Svg>,
  mic: (p: IconProps) => <Svg {...p}><rect x='9' y='3' width='6' height='11' rx='3' /><path d='M6 11a6 6 0 0 0 12 0M12 17v4M9 21h6' /></Svg>,
  clock: (p: IconProps) => <Svg {...p}><circle cx='12' cy='12' r='9' /><path d='M12 7v6l4 2' /></Svg>,
  check: (p: IconProps) => <Svg {...p}><path d='m5 12 4 4 10-10' /></Svg>,
  alert: (p: IconProps) => <Svg {...p}><path d='M12 8v5M12 17h.01' /><path d='M10.3 3.6 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.6a2 2 0 0 0-3.4 0Z' /></Svg>,
  lock: (p: IconProps) => <Svg {...p}><rect x='5' y='11' width='14' height='10' rx='2' /><path d='M8 11V8a4 4 0 1 1 8 0v3' /></Svg>,
  plusCircle: (p: IconProps) => <Svg {...p}><circle cx='12' cy='12' r='9' /><path d='M12 8v8M8 12h8' /></Svg>,
}

const BRAND_ICON_MAP: Record<string, { icon: IconType; className: string }> = {
  slack: { icon: SiSlack, className: 'text-[#E01E5A]' },
  discord: { icon: SiDiscord, className: 'text-[#5865F2]' },
  telegram: { icon: SiTelegram, className: 'text-[#24A1DE]' },
  'web-search': { icon: LuGlobe, className: 'text-blue-200' },
  filesystem: { icon: LuFolder, className: 'text-zinc-200' },
  'code-exec': { icon: LuCode, className: 'text-emerald-200' },
  custom: { icon: LuPlus, className: 'text-blue-200' },
}

export function BrandIcon({ id, className = 'h-4 w-4' }: { id: string; className?: string }) {
  const entry = BRAND_ICON_MAP[id] ?? { icon: LuLock, className: 'text-zinc-100' }
  const Icon = entry.icon
  return <Icon className={`${className} ${entry.className}`} aria-hidden='true' />
}
