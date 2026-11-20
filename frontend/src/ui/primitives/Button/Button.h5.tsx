/**
 * Button — H5 (MUI 9.5.0).
 */
import { Button as MuiButton } from '@mui/material'
import type { ButtonProps } from './Button.types'

export default function Button(props: ButtonProps) {
  const {
    variant = 'primary',
    size = 'medium',
    loading,
    disabled,
    block,
    onClick,
    ariaLabel,
    children,
  } = props
  const muiVariant =
    variant === 'outline' ? 'outlined' : variant === 'ghost' ? 'text' : 'contained'
  const color = variant === 'danger' ? 'error' : 'primary'
  return (
    <MuiButton
      variant={muiVariant}
      color={color}
      size={size}
      fullWidth={block}
      loading={loading}
      disabled={disabled}
      onClick={() => onClick?.()}
      aria-label={ariaLabel}
    >
      {children}
    </MuiButton>
  )
}
