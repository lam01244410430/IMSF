/**
 * Button — WeChat Mini Program (NutUI React 3.0.20).
 * NutUI Button KHÔNG nhận aria-label / data-testid trong kiểu của nó nên
 * 2 props đó chỉ có tác dụng ở bản H5 (xem Button.h5.tsx).
 */
import { Button as NutButton } from '@nutui/nutui-react-taro'
import type { ButtonProps } from './Button.types'

export default function Button(props: ButtonProps) {
  const {
    variant = 'primary',
    size = 'medium',
    loading,
    disabled,
    block,
    onClick,
    children,
  } = props
  const type = variant === 'danger' ? 'danger' : variant === 'primary' ? 'primary' : 'default'
  const fill = variant === 'outline' ? 'outline' : variant === 'ghost' ? 'none' : 'solid'
  const nutSize = size === 'large' ? 'large' : size === 'small' ? 'small' : 'normal'
  return (
    <NutButton
      type={type}
      fill={fill}
      shape='round'
      size={nutSize}
      block={block}
      loading={loading}
      disabled={disabled || loading}
      onClick={() => onClick?.()}
    >
      {children}
    </NutButton>
  )
}
