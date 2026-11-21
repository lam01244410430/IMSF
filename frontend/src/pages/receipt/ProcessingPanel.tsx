/**
 * ProcessingPanel — Màn 02 处理中 (§5.2): checklist 3 bước determinate
 * (KHÔNG % giả), đồng hồ đã trôi, soft/hard timeout, failure, success
 * tại chỗ (completed). 重新识别 ẨN (D-F2 — backend không có endpoint
 * reprocess, §10.2).
 *
 * Ánh xạ bước từ status (API chỉ cho pending/processing, không có sub-step):
 * pending → bước 1 active; processing → bước 1 xong, bước 2 active, bước 3 chờ.
 */
import { Image, Text, View } from '@tarojs/components'
import Taro from '@tarojs/taro'
import Button from '../../ui/primitives/Button'
import Icon from '../../ui/primitives/Icon'
import Progress from '../../ui/primitives/Progress'
import Skeleton from '../../ui/primitives/Skeleton'
import { useReceiptImage } from './useReceiptImage'
import type { ReceiptDetail } from '../../services/receipts'
import { formatElapsed, formatRelativeDate } from '../../utils/format'
import { useUiStore } from '../../store/ui'
import { goBackOrUpload, goFridge, goUpload } from '../../config/routes'
import { tokens } from '../../ui/tokens'

const STEPS = [
  { label: '正在识别文字 (OCR)', hint: '正在读取小票上的文字…' },
  { label: '正在匹配食材', hint: '正在把商品对应到食材库…' },
  { label: '正在核对总价', hint: '正在核对小票总价与明细…' },
] as const

type StepState = 'done' | 'active' | 'waiting'

function stepStates(status: string): StepState[] {
  if (status === 'processing') return ['done', 'active', 'waiting']
  return ['active', 'waiting', 'waiting']
}

function StepIcon({ state }: { state: StepState }) {
  if (state === 'done') {
    return (
      <View
        style={{
          width: 24,
          height: 24,
          borderRadius: 12,
          backgroundColor: tokens.color.accentContainer,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <Icon name='check' size={14} color={tokens.color.accent} />
      </View>
    )
  }
  if (state === 'active') {
    return (
      <View style={{ width: 24, height: 24, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <View
          className='imsf-pulse-dot'
          style={{ width: 12, height: 12, borderRadius: 6, backgroundColor: tokens.color.accent }}
        />
      </View>
    )
  }
  return (
    <View style={{ width: 24, height: 24, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <View
        style={{
          width: 12,
          height: 12,
          borderRadius: 6,
          borderWidth: 1.5,
          borderStyle: 'solid',
          borderColor: tokens.color.outline,
        }}
      />
    </View>
  )
}

export interface ProcessingPanelProps {
  detail: ReceiptDetail
  jobElapsedMs: number
  isSoftTimeout: boolean
  isHardTimeout: boolean
}

export default function ProcessingPanel({ detail, jobElapsedMs, isSoftTimeout, isHardTimeout }: ProcessingPanelProps) {
  const imageQuery = useReceiptImage(detail.id)
  const imageSrc = imageQuery.data

  const reupload = () => {
    useUiStore.getState().setOpenCameraOnShow(true)
    void goUpload()
  }

  const storeLine =
    detail.store_name ?? detail.purchased_at
      ? `${detail.store_name ?? ''} ${formatRelativeDate(detail.purchased_at ?? detail.created_at)}`.trim()
      : `小票 #${detail.id.slice(0, 8)}`

  // --- Failure (§5.2) ------------------------------------------------------
  if (detail.status === 'failed') {
    return (
      <View
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 12,
          padding: 32,
          paddingTop: 48,
        }}
      >
        <View
          style={{
            width: 64,
            height: 64,
            borderRadius: 32,
            backgroundColor: tokens.color.errorContainer,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Icon name='close' size={28} color={tokens.color.error} />
        </View>
        <Text style={{ fontSize: 18, fontWeight: 700, color: tokens.color.onSurface }}>识别失败</Text>
        <Text style={{ fontSize: 14, color: tokens.color.onSurfaceVariant, textAlign: 'center' }}>
          {detail.error_message || '识别失败，请重新拍摄或上传更清晰的图片。'}
        </Text>
        <View style={{ marginTop: 8, width: '100%' }}>
          <Button variant='primary' size='large' block onClick={reupload}>
            重新上传
          </Button>
        </View>
        {imageSrc ? (
          <Text
            style={{ fontSize: 14, color: tokens.color.accent, marginTop: 4 }}
            onClick={() => void Taro.previewImage({ current: imageSrc, urls: [imageSrc] })}
          >
            查看小票图片
          </Text>
        ) : null}
      </View>
    )
  }

  // --- Success tại chỗ (completed, §5.2) ------------------------------------
  if (detail.status === 'completed') {
    return (
      <View
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 12,
          padding: 32,
          paddingTop: 48,
        }}
      >
        <View
          style={{
            width: 64,
            height: 64,
            borderRadius: 32,
            backgroundColor: tokens.color.accentContainer,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Icon name='check' size={28} color={tokens.color.accent} />
        </View>
        <Text style={{ fontSize: 18, fontWeight: 700, color: tokens.color.onSurface }}>识别完成</Text>
        <Text style={{ fontSize: 14, color: tokens.color.onSurfaceVariant }}>
          已入库 {detail.inventory_created} 件食材
        </Text>
        <View style={{ marginTop: 8, width: '100%' }}>
          <Button variant='primary' size='large' block onClick={() => void goFridge()}>
            查看冰箱
          </Button>
        </View>
        <Button variant='ghost' onClick={() => void goUpload()}>
          返回首页
        </Button>
      </View>
    )
  }

  // --- Hard timeout (§5.2): dừng poll, KHÔNG đánh failed phía client --------
  if (isHardTimeout) {
    return (
      <View
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 12,
          padding: 32,
          paddingTop: 48,
        }}
      >
        <Icon name='clock' size={48} color={tokens.color.onSurfaceVariant} />
        <Text style={{ fontSize: 18, fontWeight: 700, color: tokens.color.onSurface }}>处理超时</Text>
        <Text style={{ fontSize: 14, color: tokens.color.onSurfaceVariant, textAlign: 'center' }}>
          服务器仍在处理或已中断。您可以稍后回来查看，或重新上传。
        </Text>
        <View style={{ marginTop: 8, width: '100%', display: 'flex', flexDirection: 'column', gap: 12 }}>
          <Button variant='primary' size='large' block onClick={reupload}>
            重新上传
          </Button>
          <Button variant='outline' size='large' block onClick={() => void goUpload()}>
            稍后查看
          </Button>
        </View>
      </View>
    )
  }

  // --- Processing (pending / processing) ------------------------------------
  const states = stepStates(detail.status)
  return (
    <View
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 16,
        padding: 24,
        paddingTop: 32,
      }}
    >
      {imageQuery.isLoading ? (
        <Skeleton variant='block' width={120} height={160} />
      ) : imageSrc ? (
        <Image src={imageSrc} mode='aspectFill' style={{ width: 120, height: 160, borderRadius: 12 }} />
      ) : null}
      <Text style={{ fontSize: 15, fontWeight: 600, color: tokens.color.onSurface }}>{storeLine}</Text>

      <View style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 12 }}>
        {STEPS.map((step, i) => {
          const state = states[i]
          return (
            <View key={step.label}>
              <View style={{ display: 'flex', flexDirection: 'row', alignItems: 'center', gap: 12 }}>
                <StepIcon state={state} />
                <Text
                  style={{
                    fontSize: 15,
                    fontWeight: state === 'active' ? 600 : 400,
                    color: state === 'waiting' ? tokens.color.onSurfaceVariant : tokens.color.onSurface,
                  }}
                >
                  {step.label}
                </Text>
              </View>
              {state === 'active' ? (
                <Text style={{ fontSize: 13, color: tokens.color.onSurfaceVariant, marginLeft: 36, marginTop: 2 }}>
                  {step.hint}
                </Text>
              ) : null}
            </View>
          )
        })}
      </View>

      <View style={{ width: '100%' }}>
        <Progress ariaLabel='正在处理' />
      </View>

      <Text style={{ fontSize: 14, color: tokens.color.onSurfaceVariant, fontVariantNumeric: 'tabular-nums' }}>
        已用时 {formatElapsed(Math.floor(jobElapsedMs / 1000))}
      </Text>
      <Text style={{ fontSize: 13, color: tokens.color.onSurfaceVariant, textAlign: 'center' }}>
        {isSoftTimeout
          ? '处理时间比平时长，请稍等，或先去看看别的。'
          : '通常需要 30 秒到 2 分钟，请稍等。'}
      </Text>

      {isSoftTimeout ? (
        <Button variant='primary' size='large' block onClick={() => void goBackOrUpload()}>
          先去看看别的，好了通知我
        </Button>
      ) : (
        <Button variant='ghost' onClick={() => void goBackOrUpload()}>
          先去看看别的，好了通知我
        </Button>
      )}
    </View>
  )
}
