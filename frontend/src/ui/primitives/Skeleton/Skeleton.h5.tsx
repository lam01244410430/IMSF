/**
 * Skeleton — H5 (MUI Skeleton).
 */
import { Skeleton as MuiSkeleton, Box } from '@mui/material'
import type { SkeletonProps } from './Skeleton.types'

export default function Skeleton(props: SkeletonProps) {
  const { rows = 3, height, width, variant = 'row', animated = true } = props
  if (variant === 'block') {
    return (
      <MuiSkeleton
        variant='rectangular'
        height={height}
        width={width}
        animation={animated ? 'wave' : false}
      />
    )
  }
  return (
    <Box>
      {Array.from({ length: rows }, (_, i) => (
        <MuiSkeleton
          key={i}
          variant='text'
          height={height}
          width={width}
          animation={animated ? 'wave' : false}
        />
      ))}
    </Box>
  )
}
