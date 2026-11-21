/**
 * Progress — WeChat Mini Program (NutUI React 3.0.20 Progress).
 * Indeterminate: NutUI không có variant riêng — dùng active (chạy liên tục).
 */
import { Progress as NutProgress } from '@nutui/nutui-react-taro'
import { tokens } from '../../tokens'
import type { ProgressProps } from './Progress.types'

export default function Progress(props: ProgressProps) {
  const { value } = props
  return (
    <NutProgress
      percent={value ?? 0}
      active={value === undefined}
      showText={false}
      background={tokens.color.surfaceVariant}
      color={tokens.color.accent}
      strokeWidth='4px'
    />
  )
}
