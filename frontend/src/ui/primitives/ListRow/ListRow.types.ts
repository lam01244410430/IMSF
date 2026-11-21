/**
 * ListRow — props dùng chung (design doc §8.2).
 * chip là ReactNode do business component StatusChip (Step 4) cung cấp —
 * primitive không tự quyết định màu/trạng thái.
 */
import type { ReactNode } from 'react'

export interface ListRowProps {
  /** Custom leading node (e.g. the 40px store-glyph circle, §5.1). */
  left?: ReactNode
  title: string
  subtitle?: string
  amount?: string
  chip?: ReactNode
  onClick?: () => void
}

export default ListRowProps
