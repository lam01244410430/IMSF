import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  Check,
  Clock,
  Close,
  Failure,
  Image as ImageIcon,
  Photograph,
  Plus,
  Refresh,
  Search,
  Tips,
  Warning,
} from '@nutui/icons-react-taro'
import type { IconProps } from './Icon.types'

const ICONS = {
  camera: Photograph,
  'chevron-left': ArrowLeft,
  'chevron-right': ArrowRight,
  'chevron-down': ArrowDown,
  check: Check,
  clock: Clock,
  close: Close,
  error: Failure,
  image: ImageIcon,
  plus: Plus,
  refresh: Refresh,
  search: Search,
  warning: Warning,
  info: Tips,
} as const

/** Icon (weapp) — NutUI icons. Icon key set matches the H5 twin exactly. */
export default function Icon({ name, size = 24, color }: IconProps) {
  const NutIcon = ICONS[name]
  return <NutIcon width={size} height={size} color={color} />
}
