/**
 * Progress — H5 (MUI LinearProgress).
 */
import { LinearProgress } from '@mui/material'
import type { ProgressProps } from './Progress.types'

export default function Progress(props: ProgressProps) {
  const { value, ariaLabel } = props
  return (
    <LinearProgress
      variant={value === undefined ? 'indeterminate' : 'determinate'}
      value={value}
      aria-label={ariaLabel}
    />
  )
}
