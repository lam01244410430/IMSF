/**
 * ReceiptList — danh sách tiểu phiếu dùng chung (§5.1, §7.2): 3 skeleton row
 * khi load lần đầu >300ms (cha truyền showSkeleton), panel lỗi + [重试],
 * empty state do cha truyền, các row (giới hạn qua `limit`).
 */
import { Text, View } from '@tarojs/components'
import type { ReactNode } from 'react'
import { tokens } from '../../ui/tokens'
import Button from '../../ui/primitives/Button'
import Skeleton from '../../ui/primitives/Skeleton'
import ReceiptRow from '../ReceiptRow/ReceiptRow'
import type { Receipt } from '../../services/receipts'

export interface ReceiptListProps {
  receipts: Receipt[]
  isLoading: boolean
  showSkeleton: boolean
  isError: boolean
  onRetry: () => void
  onSelect: (receipt: Receipt) => void
  emptyState?: ReactNode
  limit?: number
}

function SkeletonRow() {
  return (
    <View style={{ display: 'flex', flexDirection: 'row', alignItems: 'center', gap: 12, padding: 16 }}>
      <Skeleton variant='block' width={40} height={40} />
      <View style={{ display: 'flex', flexDirection: 'column', gap: 6, flex: 1 }}>
        <Skeleton variant='block' width='60%' height={14} />
        <Skeleton variant='block' width='40%' height={12} />
      </View>
      <Skeleton variant='block' width={64} height={14} />
    </View>
  )
}

export default function ReceiptList(props: ReceiptListProps) {
  const { receipts, isLoading, showSkeleton, isError, onRetry, onSelect, emptyState, limit } = props
  if (isError) {
    return (
      <View
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 12,
          paddingTop: 48,
          paddingBottom: 48,
          paddingLeft: 24,
          paddingRight: 24,
        }}
      >
        <Text style={{ fontSize: 14, color: tokens.color.onSurfaceVariant, textAlign: 'center' }}>
          加载失败，请检查网络后重试
        </Text>
        <Button variant='outline' onClick={onRetry}>
          重试
        </Button>
      </View>
    )
  }
  if (isLoading && showSkeleton) {
    return (
      <View>
        <SkeletonRow />
        <SkeletonRow />
        <SkeletonRow />
      </View>
    )
  }
  if (receipts.length === 0) {
    return <View>{emptyState}</View>
  }
  const shown = limit ? receipts.slice(0, limit) : receipts
  return (
    <View>
      {shown.map((receipt) => (
        <ReceiptRow key={receipt.id} receipt={receipt} onClick={() => onSelect(receipt)} />
      ))}
    </View>
  )
}
