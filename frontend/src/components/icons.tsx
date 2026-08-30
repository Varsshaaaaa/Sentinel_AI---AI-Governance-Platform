import type { SVGProps } from 'react'

type IconProps = SVGProps<SVGSVGElement>

const base = (props: IconProps) => ({
  width: 18,
  height: 18,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.8,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  ...props,
})

export const IconShield = (p: IconProps) => (
  <svg {...base(p)}><path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6l7-3z" /></svg>
)
export const IconGrid = (p: IconProps) => (
  <svg {...base(p)}><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></svg>
)
export const IconRobot = (p: IconProps) => (
  <svg {...base(p)}><rect x="4" y="8" width="16" height="12" rx="3" /><path d="M12 8V4M9 4h6M9 14h.01M15 14h.01" /></svg>
)
export const IconGraph = (p: IconProps) => (
  <svg {...base(p)}><circle cx="6" cy="6" r="2.5" /><circle cx="18" cy="7" r="2.5" /><circle cx="12" cy="18" r="2.5" /><path d="M8 7.5l7 8M16 9l-4 6.5" /></svg>
)
export const IconFirewall = (p: IconProps) => (
  <svg {...base(p)}><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M3 9h18M3 15h18M9 4v5M15 9v6M9 15v5" /></svg>
)
export const IconScroll = (p: IconProps) => (
  <svg {...base(p)}><path d="M6 3h10a2 2 0 0 1 2 2v13a3 3 0 0 0 3 3H8a2 2 0 0 1-2-2V3z" /><path d="M6 3a2 2 0 0 0-2 2v2h2M10 8h6M10 12h6M10 16h4" /></svg>
)
export const IconFlask = (p: IconProps) => (
  <svg {...base(p)}><path d="M9 3h6M10 3v6l-5 8a2 2 0 0 0 1.7 3h10.6a2 2 0 0 0 1.7-3l-5-8V3" /><path d="M7.5 15h9" /></svg>
)
export const IconUsersCheck = (p: IconProps) => (
  <svg {...base(p)}><circle cx="9" cy="8" r="3" /><path d="M3 20a6 6 0 0 1 11 0M16 11l2 2 4-4" /></svg>
)
export const IconAlert = (p: IconProps) => (
  <svg {...base(p)}><path d="M12 3l9 16H3l9-16z" /><path d="M12 10v4M12 17h.01" /></svg>
)
export const IconReplay = (p: IconProps) => (
  <svg {...base(p)}><path d="M3 12a9 9 0 1 0 3-6.7L3 8" /><path d="M3 4v4h4" /></svg>
)
export const IconActivity = (p: IconProps) => (
  <svg {...base(p)}><path d="M3 12h4l2 6 4-14 2 8h6" /></svg>
)
export const IconBook = (p: IconProps) => (
  <svg {...base(p)}><path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2V5z" /><path d="M19 3v18" /></svg>
)
export const IconMenu = (p: IconProps) => (
  <svg {...base(p)}><path d="M4 6h16M4 12h16M4 18h16" /></svg>
)
export const IconSidebar = (p: IconProps) => (
  <svg {...base(p)}><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M9 4v16" /></svg>
)
export const IconRefresh = (p: IconProps) => (
  <svg {...base(p)}><path d="M21 12a9 9 0 1 1-2.6-6.4M21 3v4h-4" /></svg>
)
export const IconClock = (p: IconProps) => (
  <svg {...base(p)}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>
)
export const IconBolt = (p: IconProps) => (
  <svg {...base(p)}><path d="M13 2L4 14h7l-1 8 9-12h-7l1-8z" /></svg>
)
export const IconInfo = (p: IconProps) => (
  <svg {...base(p)}><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></svg>
)
export const IconUp = (p: IconProps) => (
  <svg {...base(p)}><path d="M12 19V5M6 11l6-6 6 6" /></svg>
)
export const IconDown = (p: IconProps) => (
  <svg {...base(p)}><path d="M12 5v14M6 13l6 6 6-6" /></svg>
)
export const IconInbox = (p: IconProps) => (
  <svg {...base(p)}><path d="M3 13l3-9h12l3 9v6a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-6z" /><path d="M3 13h5l1 3h6l1-3h5" /></svg>
)
export const IconSearch = (p: IconProps) => (
  <svg {...base(p)}><circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" /></svg>
)
export const IconExternal = (p: IconProps) => (
  <svg {...base(p)}><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" /></svg>
)
