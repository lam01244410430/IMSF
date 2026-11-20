/**
 * Stepper — H5 (MUI: IconButton − / TextField / IconButton +).
 */
import { Box, IconButton, TextField } from '@mui/material'
import { Add, Remove } from '@mui/icons-material'
import { tokens } from '../../tokens'
import type { StepperProps } from './Stepper.types'

export default function Stepper(props: StepperProps) {
  const { value, onChange, min = 0, max, step = 1, disabled, ariaLabel } = props
  const clamp = (v: number) => Math.min(max ?? Number.POSITIVE_INFINITY, Math.max(min, v))
  const dec = () => onChange(clamp(value - step))
  const inc = () => onChange(clamp(value + step))
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: tokens.spacing.minTouchGap }}>
      <IconButton
        size='small'
        onClick={dec}
        disabled={disabled || value <= min}
        aria-label='giảm'
      >
        <Remove />
      </IconButton>
      <TextField
        value={value}
        onChange={(e) => {
          const n = Number(e.target.value)
          if (!Number.isNaN(n)) onChange(clamp(n))
        }}
        type='number'
        size='small'
        disabled={disabled}
        slotProps={{ htmlInput: { min, max, step, 'aria-label': ariaLabel ?? 'số lượng' } }}
        sx={{ width: 72 }}
      />
      <IconButton
        size='small'
        onClick={inc}
        disabled={disabled || (max !== undefined && value >= max)}
        aria-label='tăng'
      >
        <Add />
      </IconButton>
    </Box>
  )
}
