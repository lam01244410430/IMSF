import {
  AccessTime,
  Add,
  Check,
  ChevronLeft,
  ChevronRight,
  Close,
  Error,
  ExpandMore,
  Image,
  Info,
  PhotoCamera,
  Refresh,
  Search,
  Warning,
} from '@mui/icons-material'
import type { IconProps } from './Icon.types'

const ICONS = {
  camera: PhotoCamera,
  'chevron-left': ChevronLeft,
  'chevron-right': ChevronRight,
  'chevron-down': ExpandMore,
  check: Check,
  clock: AccessTime,
  close: Close,
  error: Error,
  image: Image,
  plus: Add,
  refresh: Refresh,
  search: Search,
  warning: Warning,
  info: Info,
} as const

/** Icon (H5) — MUI icons. Icon key set matches the weapp twin exactly. */
export default function Icon({ name, size = 24, color }: IconProps) {
  const MuiIcon = ICONS[name]
  return <MuiIcon sx={{ fontSize: size, color }} />
}
