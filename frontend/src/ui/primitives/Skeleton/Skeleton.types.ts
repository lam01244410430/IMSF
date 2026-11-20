/**
 * Skeleton — props dùng chung (design doc §8.2).
 * variant 'row': dòng chữ; 'block': khối chữ nhật (vd ảnh / card).
 */
export interface SkeletonProps {
  rows?: number
  height?: number
  width?: number | string
  variant?: 'row' | 'block'
  animated?: boolean
}

export default SkeletonProps
