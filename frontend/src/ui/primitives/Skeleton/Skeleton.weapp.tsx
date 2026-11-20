/**
 * Skeleton — WeChat Mini Program (NutUI React 3.0.20 Skeleton).
 */
import { Skeleton as NutSkeleton } from '@nutui/nutui-react-taro'
import type { SkeletonProps } from './Skeleton.types'

export default function Skeleton(props: SkeletonProps) {
  const { rows = 3, height, width, variant = 'row', animated = true } = props
  // NutUI Skeleton: visible=true nghĩa là HIỆN NỘI DUNG (ẩn skeleton).
  // Primitive này luôn hiển thị skeleton nên visible=false.
  // height/width chỉ truyền khi có giá trị (spread ghi đè default).
  return (
    <NutSkeleton
      rows={variant === 'block' ? 1 : rows}
      animated={animated}
      visible={false}
      {...(height !== undefined ? { height } : {})}
      {...(width !== undefined ? { width } : {})}
    />
  )
}
