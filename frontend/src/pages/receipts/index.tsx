/**
 * 全部小票 — danh sách đầy đủ (§5.1): filter chip theo trạng thái
 * (全部/处理中/需核对/已完成/识别失败) + ReceiptList dùng chung. Trang thường
 * (không phải tab) — không render TabBarHost, header có nút back.
 */
import { useEffect, useState } from 'react'
import { Text, View } from '@tarojs/components'
import { useQuery } from '@tanstack/react-query'
import PageHeader from '../../components/PageHeader/PageHeader'
import OfflineBanner from '../../components/OfflineBanner/OfflineBanner'
import ReceiptList from '../../components/ReceiptList/ReceiptList'
import EmptyState from '../../components/EmptyState/EmptyState'
import Button from '../../ui/primitives/Button'
import { useSessionStore } from '../../store/session'
import { listReceipts, type Receipt, type ReceiptStatus } from '../../services/receipts'
import { goBack, goReceipt, goUpload } from '../../config/routes'
import { tokens } from '../../ui/tokens'

type Filter = 'all' | ReceiptStatus

const FILTERS: { key: Filter; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'processing', label: '处理中' },
  { key: 'needs_review', label: '需核对' },
  { key: 'completed', label: '已完成' },
  { key: 'failed', label: '识别失败' },
]

export default function Receipts() {
  const householdId = useSessionStore((s) => s.currentHouseholdId)
  const [filter, setFilter] = useState<Filter>('all')
  // Backend chỉ lọc đúng một status (§5.1 API) — chip「处理中」gộp cả
  // pending + processing nên lọc ở client (limit 20, GĐ1).
  const query = useQuery({
    queryKey: ['receipts', householdId, 'all'],
    queryFn: () => listReceipts(householdId as string, { limit: 20 }),
    enabled: Boolean(householdId),
  })
  const filtered =
    filter === 'all'
      ? query.data ?? []
      : (query.data ?? []).filter((r) =>
          filter === 'processing' ? r.status === 'pending' || r.status === 'processing' : r.status === filter,
        )

  // Skeleton chỉ hiện khi load lần đầu >300ms (§7.2).
  const [showSkeleton, setShowSkeleton] = useState(false)
  useEffect(() => {
    if (!query.isLoading) {
      setShowSkeleton(false)
      return
    }
    const t = setTimeout(() => setShowSkeleton(true), 300)
    return () => clearTimeout(t)
  }, [query.isLoading])

  const handleSelect = (receipt: Receipt) => {
    void goReceipt(receipt.id)
  }

  return (
    <View>
      <PageHeader title='全部小票' showBack onBack={() => void goBack()} />
      <OfflineBanner />
      <View
        style={{
          display: 'flex',
          flexDirection: 'row',
          flexWrap: 'wrap',
          gap: 8,
          paddingTop: 12,
          paddingBottom: 4,
          paddingLeft: 16,
          paddingRight: 16,
        }}
      >
        {FILTERS.map((f) => (
          <Button
            key={f.key}
            variant={filter === f.key ? 'primary' : 'outline'}
            size='small'
            onClick={() => setFilter(f.key)}
          >
            {f.label}
          </Button>
        ))}
      </View>
      <View style={{ paddingLeft: 8, paddingRight: 8, paddingBottom: 16 }}>
        {!householdId ? (
          <Text style={{ fontSize: 14, color: tokens.color.onSurfaceVariant, padding: 16 }}>
            请先登录后查看小票
          </Text>
        ) : (
          <ReceiptList
            receipts={filtered}
            isLoading={query.isLoading}
            showSkeleton={showSkeleton}
            isError={query.isError}
            onRetry={() => void query.refetch()}
            onSelect={handleSelect}
            emptyState={
              <EmptyState
                icon='camera'
                title='还没有小票'
                body='拍下第一张小票，自动记账并同步到冰箱。'
                actionLabel='立即拍照'
                onAction={() => void goUpload()}
              />
            }
          />
        )}
      </View>
    </View>
  )
}
