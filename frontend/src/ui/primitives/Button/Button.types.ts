/**
 * Button — props dùng chung cho cả 2 platform (design doc §8.2).
 * variant: primary (contained xanh), outline, ghost (text), danger.
 */
import type { ReactNode } from 'react'

export type ButtonVariant = 'primary' | 'outline' | 'ghost' | 'danger'
export type ButtonSize = 'large' | 'medium' | 'small'

export interface ButtonProps {
  variant?: ButtonVariant
  size?: ButtonSize
  loading?: boolean
  disabled?: boolean
  block?: boolean
  onClick?: () => void
  ariaLabel?: string
  children: ReactNode
}

export default ButtonProps
