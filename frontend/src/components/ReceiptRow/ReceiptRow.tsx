/**
 * ReceiptRow — một dòng tiểu phiếu (§5.1): vòng tròn glyph 40px
 * (primaryContainer) + tên cửa hàng + ngày tương đối + số tiền + StatusChip.
 * Số tiền chỉ hiển thị khi đã biết (completed/needs_review), còn lại 「—」.
 */
import { Text, View } from '@tarojs/components'
import { tokens } from '../../ui/tokens'
import ListRow from '../../ui/primitives/ListRow'
import StatusChip from '../StatusChip/StatusChip'
import { formatMoney, formatRelativeDate, storeGlyph } from '../../utils/format'
import type { Receipt } from '../../services/receipts'

export interface ReceiptRowProps {
  receipt: Receipt
  onClick: () => void
}

export default function ReceiptRow({ receipt, onClick }: ReceiptRowProps) {
  const amountKnown = receipt.status === 'completed' || receipt.status === 'needs_review'
  // API trả currency dạng string tự do; client chỉ hỗ trợ CNY/VND (§3.2) —
  // currency lạ mặc định về CNY (China-first).
  const currency = receipt.currency === 'VND' ? 'VND' : 'CNY'
  const amount = amountKnown ? formatMoney(receipt.total_amount, currency) : '—'
  return (
    <ListRow
      left={
        <View
          style={{
            width: 40,
            height: 40,
            borderRadius: 20,
            backgroundColor: tokens.color.primaryContainer,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
          }}
        >
          <Text style={{ fontSize: 15, fontWeight: 600, color: tokens.color.onPrimaryContainer }}>
            {storeGlyph(receipt.store_name)}
          </Text>
        </View>
      }
      title={receipt.store_name ?? '未知商家'}
      subtitle={formatRelativeDate(receipt.purchased_at ?? receipt.created_at)}
      amount={amount}
      chip={<StatusChip status={receipt.status} />}
      onClick={onClick}
    />
  )
}
