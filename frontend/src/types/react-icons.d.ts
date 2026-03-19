declare module 'react-icons' {
  import type { SVGProps } from 'react'

  export type IconType = (props: SVGProps<SVGSVGElement> & {
    title?: string
    size?: string | number
    color?: string
  }) => JSX.Element
}

declare module 'react-icons/fa' {
  import type { IconType } from 'react-icons'

  export const FaDiscord: IconType
  export const FaFolder: IconType
  export const FaGlobe: IconType
  export const FaLock: IconType
  export const FaPlus: IconType
  export const FaSlack: IconType
  export const FaTelegram: IconType
  export const FaTerminal: IconType
  export const FaTimes: IconType
}

declare module 'react-icons/fc' {
  import type { IconType } from 'react-icons'

  export const FcGoogle: IconType
}

declare module 'react-icons/si' {
  import type { IconType } from 'react-icons'

  export const SiDiscord: IconType
  export const SiSlack: IconType
  export const SiTelegram: IconType
}

declare module 'react-icons/lu' {
  import type { IconType } from 'react-icons'

  export const LuActivity: IconType
  export const LuArrowUpRight: IconType
  export const LuBot: IconType
  export const LuBrainCircuit: IconType
  export const LuCalendar: IconType
  export const LuChartBar: IconType
  export const LuChartPie: IconType
  export const LuChevronDown: IconType
  export const LuChevronUp: IconType
  export const LuCode: IconType
  export const LuCreditCard: IconType
  export const LuDownload: IconType
  export const LuFilter: IconType
  export const LuFolder: IconType
  export const LuGlobe: IconType
  export const LuLoader: IconType
  export const LuLock: IconType
  export const LuPlus: IconType
  export const LuShield: IconType
  export const LuTrendingUp: IconType
  export const LuTriangleAlert: IconType
  export const LuWind: IconType
  export const LuX: IconType
  export const LuZap: IconType
}
