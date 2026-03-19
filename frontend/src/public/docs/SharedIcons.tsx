/* eslint-disable react-refresh/only-export-components */
import type { ReactNode } from 'react'

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

export const SharedIcons = {
  search: (p: IconProps) => <Svg {...p}><circle cx='11' cy='11' r='6' /><path d='m20 20-3.5-3.5' /></Svg>,
  globe: (p: IconProps) => <Svg {...p}><circle cx='12' cy='12' r='9' /><path d='M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18' /></Svg>,
  workflows: (p: IconProps) => <Svg {...p}><circle cx='5' cy='6' r='2' /><circle cx='19' cy='6' r='2' /><circle cx='12' cy='18' r='2' /><path d='M7 7.5l3.5 7M17 7.5l-3.5 7' /></Svg>,
  star: (p: IconProps) => <Svg {...p}><path d='m12 3 2.7 5.5 6 .9-4.3 4.2 1 5.9-5.4-2.8-5.4 2.8 1-5.9L3.3 9.4l6-.9z' /></Svg>,
  check: (p: IconProps) => <Svg {...p}><path d='m5 12 4 4 10-10' /></Svg>,
}
