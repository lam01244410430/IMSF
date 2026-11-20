/**
 * TextField — H5 (MUI 9.5.0 TextField).
 */
import { TextField as MuiTextField } from '@mui/material'
import type { TextFieldProps } from './TextField.types'

export default function TextField(props: TextFieldProps) {
  const {
    label,
    value,
    onChange,
    type = 'text',
    inputMode,
    placeholder,
    error,
    helperText,
    disabled,
    maxLength,
    ariaLabel,
  } = props
  return (
    <MuiTextField
      label={label}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      type={type}
      placeholder={placeholder}
      error={Boolean(error)}
      helperText={error ?? helperText}
      disabled={disabled}
      fullWidth
      slotProps={{ htmlInput: { maxLength, inputMode } }}
      aria-label={ariaLabel}
    />
  )
}
