/**
 * Icon — shared props for the Icon adapter primitive (design doc §8.2:
 * "thêm khi cần"). Icons are render-only (no state): NutUI icons on weapp,
 * MUI icons on H5, same key set on both targets.
 */
export type IconName =
  | 'camera'
  | 'chevron-left'
  | 'chevron-right'
  | 'check'
  | 'clock'
  | 'close'
  | 'error'
  | 'image'
  | 'plus'
  | 'refresh'
  | 'search'
  | 'warning'
  | 'info'

export interface IconProps {
  /** Semantic icon key (not a platform icon name). */
  name: IconName
  /** Icon size in px (both width and height). Default 24. */
  size?: number
  /** Icon colour (token hex). Default inherits currentColor. */
  color?: string
}

export default IconProps
