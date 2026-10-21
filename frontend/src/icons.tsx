import type { SVGProps } from 'react'

type P = SVGProps<SVGSVGElement>

const base = (props: P) => ({
  width: 18,
  height: 18,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.7,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  ...props,
})

export const IconSend = (p: P) => (
  <svg {...base(p)}>
    <path d="M4.5 12h13M12.5 6l6 6-6 6" />
  </svg>
)

export const IconMic = (p: P) => (
  <svg {...base(p)}>
    <rect x="9" y="3" width="6" height="11" rx="3" />
    <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
  </svg>
)

export const IconImage = (p: P) => (
  <svg {...base(p)}>
    <rect x="3" y="4" width="18" height="16" rx="3" />
    <circle cx="8.5" cy="9.5" r="1.5" />
    <path d="m3.5 17 4.2-4.2a2 2 0 0 1 2.8 0L15 17.5m0 0 1.7-1.7a2 2 0 0 1 2.8 0l1 1" />
  </svg>
)

export const IconChart = (p: P) => (
  <svg {...base(p)}>
    <path d="M5 19V9m7 10V5m7 14v-6" />
  </svg>
)

export const IconList = (p: P) => (
  <svg {...base(p)}>
    <path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01" />
  </svg>
)

export const IconClose = (p: P) => (
  <svg {...base(p)}>
    <path d="m6 6 12 12M18 6 6 18" />
  </svg>
)

export const IconTrash = (p: P) => (
  <svg {...base(p)}>
    <path d="M4 7h16M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2m-9 0 1 12a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1l1-12" />
  </svg>
)

export const IconSpark = (p: P) => (
  <svg {...base(p)}>
    <path d="M12 3v4M12 17v4M3 12h4M17 12h4M6.3 6.3l2.6 2.6M15.1 15.1l2.6 2.6M17.7 6.3l-2.6 2.6M8.9 15.1l-2.6 2.6" />
  </svg>
)

export const IconChevron = (p: P) => (
  <svg {...base(p)}>
    <path d="m9 6 6 6-6 6" />
  </svg>
)

export const IconUp = (p: P) => (
  <svg {...base(p)}>
    <path d="M12 19V5m-6 6 6-6 6 6" />
  </svg>
)

export const IconDown = (p: P) => (
  <svg {...base(p)}>
    <path d="M12 5v14m6-6-6 6-6-6" />
  </svg>
)

export const IconLogout = (p: P) => (
  <svg {...base(p)}>
    <path d="M15 17l5-5-5-5M20 12H9M12 20H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h6" />
  </svg>
)

export const IconStop = (p: P) => (
  <svg {...base(p)}>
    <rect x="7" y="7" width="10" height="10" rx="2" fill="currentColor" stroke="none" />
  </svg>
)

/** 分类图标：线性、统一笔画，跟大厂财务类产品保持一致的气质 */
const CATEGORY_PATHS: Record<string, JSX.Element> = {
  coffee: <><path d="M4 8h12v6a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4V8Z" /><path d="M16 9h1.5a2.5 2.5 0 0 1 0 5H16M4 21h12" /></>,
  car: <><path d="M5 17h14M6 17l1.2-5.2A2 2 0 0 1 9.2 10h5.6a2 2 0 0 1 2 1.8L18 17" /><circle cx="8" cy="17.5" r="1.5" /><circle cx="16" cy="17.5" r="1.5" /><path d="M8 10l1-3h6l1 3" /></>,
  bag: <><path d="M5 8h14l-1 12H6L5 8Z" /><path d="M9 8V6a3 3 0 0 1 6 0v2" /></>,
  shirt: <><path d="M9 4 5 6l1.5 4L8 9.5V20h8V9.5L17.5 10 19 6l-4-2-1.5 1.5h-3L9 4Z" /></>,
  home: <><path d="m4 10 8-6 8 6v10a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V10Z" /><path d="M10 21v-7h4v7" /></>,
  game: <><rect x="3" y="7" width="18" height="10" rx="5" /><path d="M8 10v4M6 12h4M15.5 11h.01M18 13.5h.01" /></>,
  heart: <><path d="M12 20s-7-4.4-7-9a4 4 0 0 1 7-2.6A4 4 0 0 1 19 11c0 4.6-7 9-7 9Z" /></>,
  book: <><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H19v15H6.5A2.5 2.5 0 0 0 4 20.5V5.5Z" /><path d="M4 18.5h15V21H6.5A2.5 2.5 0 0 1 4 18.5Z" /></>,
  device: <><rect x="7" y="3" width="10" height="18" rx="2.5" /><path d="M11 18h2" /></>,
  plane: <><path d="M3 13.5 21 6l-4 12-4.5-3L8 20l-.5-4.5L3 13.5Z" /></>,
  gift: <><rect x="3" y="8" width="18" height="12" rx="2" /><path d="M3 13h18M12 8v12" /><path d="M12 8S9.5 3 7.5 4.5 9 8 12 8Zm0 0s2.5-5 4.5-3.5S15 8 12 8Z" /></>,
  dots: <><circle cx="6" cy="12" r="1.2" fill="currentColor" /><circle cx="12" cy="12" r="1.2" fill="currentColor" /><circle cx="18" cy="12" r="1.2" fill="currentColor" /></>,
}

export function CategoryIcon({ name, size = 18, ...rest }: P & { name: string; size?: number }) {
  const path = CATEGORY_PATHS[name] ?? CATEGORY_PATHS.dots
  return (
    <svg {...base({ ...rest, width: size, height: size })}>{path}</svg>
  )
}
