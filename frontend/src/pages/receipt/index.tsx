/**
 * Receipt detail — một route /receipts/{id} cho mọi trạng thái (§5.2/§5.3,
 * F13): nội dung đổi theo `status` (processing / review / completed /
 * failed), không state nào mang trong navigation params — deep link cold
 * start chạy y hệt.
 *
 * Màn 02 và Màn 03 là cùng một page instance đổi nội dung theo status, nên
 * KHÔNG cần redirectTo khi needs_review: back không bao giờ về spinner cũ
 * vì stack chỉ có một trang receipt (đúng ý đồ của doc §5.2).
 * 重新识别 ẨN ở cả hai màn (D-F2 — backend không có endpoint reprocess).
 */
import { useEffect, useState } from 'react'
import { Text, View } from '@tarojs/components'
import { useRouter } from '@tarojs/taro'
import PageHeader from '../../components/PageHeader/PageHeader'
import OfflineBanner from '../../components/OfflineBanner/OfflineBanner'
import Button from '../../ui/primitives/Button'
import Skeleton from '../../ui/primitives/Skeleton'
import ProcessingPanel from './ProcessingPanel'
import ReviewForm from './ReviewForm'
import {
  isTerminalStatus,
  RECEIPT_POLL_HARD_TIMEOUT_MS,
  RECEIPT_POLL_SOFT_TIMEOUT_MS,
  useReceiptPolling,
} from '../../services/receipts'
import { goBackOrUpload, goUpload } from '../../config/routes'
import { tokens } from '../../ui/tokens'
import './index.scss'

export default function ReceiptDetail() {
  const { params } = useRouter()
  const id = typeof params.id === 'string' ? params.id : ''
  const [hardStopped, setHardStopped] = useState(false)
  const polling = useReceiptPolling(id || null, { enabled: !hardStopped })
  const data = polling.data

  // Đồng hồ job age (ticking mỗi giây) — timeout tính từ created_at (tuổi
  // thật của job), không phải từ lúc mở màn.
  const [nowMs, setNowMs] = useState(() => Date.now())
  useEffect(() => {
    const t = setInterval(() => setNowMs(Date.now()), 1000)
    return () => clearInterval(t)
  }, [])

  const createdAtMs = data?.created_at ? new Date(data.created_at).getTime() : null
  const jobElapsedMs =
    createdAtMs !== null && !Number.isNaN(createdAtMs)
      ? Math.max(0, nowMs - createdAtMs)
      : polling.elapsedMs
  const terminal = !!data && isTerminalStatus(data.status)
  const isSoftTimeout = !!data && !terminal && jobElapsedMs >= RECEIPT_POLL_SOFT_TIMEOUT_MS
  const isHardTimeout = !!data && !terminal && jobElapsedMs >= RECEIPT_POLL_HARD_TIMEOUT_MS

  // Hard timeout: dừng polling (server vẫn sở hữu status — không bịa failed).
  useEffect(() => {
    if (isHardTimeout) setHardStopped(true)
  }, [isHardTimeout])

  const header =
    data?.status === 'needs_review' ? (
      <PageHeader title='核对小票' subtitle='请确认以下明细无误后入库' showBack onBack={() => void goBackOrUpload()} />
    ) : data?.status === 'completed' ? (
      <PageHeader title='小票详情' showBack onBack={() => void goBackOrUpload()} />
    ) : (
      <PageHeader title='处理中' showBack onBack={() => void goBackOrUpload()} />
    )

  return (
    <View>
      {header}
      <OfflineBanner />
      {!id ? (
        <View style={{ padding: 32, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12 }}>
          <Text style={{ fontSize: 14, color: tokens.color.onSurfaceVariant }}>该内容已不存在</Text>
          <Button variant='primary' onClick={() => void goUpload()}>
            返回首页
          </Button>
        </View>
      ) : polling.isLoading && !data ? (
        <View style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <Skeleton variant='block' width='100%' height={240} />
          <Skeleton variant='block' width='60%' height={14} />
          <Skeleton variant='block' width='40%' height={14} />
        </View>
      ) : polling.isError && !data ? (
        <View
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 12,
            paddingTop: 48,
            paddingLeft: 24,
            paddingRight: 24,
          }}
        >
          <Text style={{ fontSize: 14, color: tokens.color.onSurfaceVariant, textAlign: 'center' }}>
            加载失败，请检查网络后重试
          </Text>
          <Button variant='outline' onClick={() => void polling.refetch()}>
            重试
          </Button>
        </View>
      ) : data ? (
        data.status === 'needs_review' ? (
          <ReviewForm detail={data} refetch={() => void polling.refetch()} />
        ) : (
          <ProcessingPanel
            detail={data}
            jobElapsedMs={jobElapsedMs}
            isSoftTimeout={isSoftTimeout}
            isHardTimeout={isHardTimeout}
          />
        )
      ) : null}
    </View>
  )
}
