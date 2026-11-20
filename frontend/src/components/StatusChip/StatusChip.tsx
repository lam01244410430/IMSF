/**
 * StatusChip — chip trạng thái tiểu phiếu (§5.1): icon + chữ, 24px, radius
 * 12px, text 12px. Màu lấy từ tokens.status (không hardcode hex).
 */
import { Text, View } from '@tarojs/components'
import { tokens } from '../../ui/tokens'
import type { ReceiptStatus } from '../../services/receipts'

const STATUS_CONF: Record<ReceiptStatus, { glyph: string; label: string; bg: string; text: string }> = {
  completed: { glyph: '✓', label: '已完成', bg: tokens.status.completed.bg, text: tokens.status.completed.text },
  pending: { glyph: '◷', label: '处理中', bg: tokens.status.processing.bg, text: tokens.status.processing.text },
  processing: { glyph: '◷', label: '处理中', bg: tokens.status.processing.bg, text: tokens.status.processing.text },
  needs_review: { glyph: '!', label: '需核对', bg: tokens.status.needsReview.bg, text: tokens.status.needsReview.text },
  failed: { glyph: '✕', label: '识别失败', bg: tokens.status.failed.bg, text: tokens.status.failed.text },
}

export default function StatusChip({ status }: { status: ReceiptStatus }) {
  const conf = STATUS_CONF[status]
  return (
    <View
      style={{
        height: 24,
        borderRadius: 12,
        paddingLeft: 8,
        paddingRight: 8,
        backgroundColor: conf.bg,
        display: 'flex',
        flexDirection: 'row',
        alignItems: 'center',
        gap: 4,
      }}
    >
      <Text style={{ fontSize: 14, color: conf.text }}>{conf.glyph}</Text>
      <Text style={{ fontSize: 12, color: conf.text }}>{conf.label}</Text>
    </View>
  )
}
