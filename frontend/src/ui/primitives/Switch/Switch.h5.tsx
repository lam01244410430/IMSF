/**
 * Switch — H5 (MUI Switch).
 */
import { Switch as MuiSwitch } from '@mui/material'
import type { SwitchProps } from './Switch.types'

export default function Switch(props: SwitchProps) {
  const { checked, onChange, disabled, ariaLabel } = props
  return (
    <MuiSwitch
      checked={checked}
      onChange={(_, v) => onChange(v)}
      disabled={disabled}
      slotProps={{ input: { 'aria-label': ariaLabel } }}
    />
  )
}
