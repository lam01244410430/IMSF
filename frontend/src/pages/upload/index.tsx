/**
 * Screen 01 — Upload (§5.1): capture card + 拍照/从相册选择 + recent list
 * (3 dòng đầu + 查看全部) + skeleton/empty/error + pull-to-refresh.
 * Upload 202 → navigateTo /receipts/{id} + toast「小票已上传，正在识别」.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { Image, Text, View } from '@tarojs/components'
import Taro, { useDidShow, usePullDownRefresh } from '@tarojs/taro'
import { useQuery } from '@tanstack/react-query'
import PageHeader from '../../components/PageHeader/PageHeader'
import OfflineBanner from '../../components/OfflineBanner/OfflineBanner'
import ReceiptList from '../../components/ReceiptList/ReceiptList'
import EmptyState from '../../components/EmptyState/EmptyState'
import TabBarHost from '../../components/TabBarHost'
import Button from '../../ui/primitives/Button'
import Icon from '../../ui/primitives/Icon'
import Progress from '../../ui/primitives/Progress'
import { useTabBarSelected } from '../../hooks/useTabBarSelected'
import { useSessionStore } from '../../store/session'
import { useUiStore } from '../../store/ui'
import { useUploadDraftStore } from '../../store/uploadDraft'
import { listReceipts, type Receipt } from '../../services/receipts'
import { IMAGE_ERROR_ZH, pickImage, preparePickedImage, uploadReceipt } from '../../services/upload'
import { showToast } from '../../ui/primitives/Toast'
import { ApiError, apiErrorToZh } from '../../services/errors'
import { goLogin, goReceipt, goReceipts } from '../../config/routes'
import { tokens } from '../../ui/tokens'
import { withAlpha } from '../../utils/format'

type BannerAction = 'reselect' | 'reupload' | null

export default function Upload() {
  useTabBarSelected(0)
  const householdId = useSessionStore((s) => s.currentHouseholdId)
  const isOnline = useUiStore((s) => s.isOnline)
  const draft = useUploadDraftStore()
  const [error, setError] = useState<string | null>(null)
  const [errorAction, setErrorAction] = useState<BannerAction>(null)
  const [lastSource, setLastSource] = useState<'camera' | 'album'>('camera')
  const [justRefreshed, setJustRefreshed] = useState(false)

  const recentQuery = useQuery({
    queryKey: ['receipts', householdId, 'recent'],
    queryFn: () => listReceipts(householdId as string, { limit: 20 }),
    enabled: Boolean(householdId),
  })

  // Skeleton chỉ hiện khi load lần đầu >300ms (§7.2).
  const [showSkeleton, setShowSkeleton] = useState(false)
  useEffect(() => {
    if (!recentQuery.isLoading) {
      setShowSkeleton(false)
      return
    }
    const t = setTimeout(() => setShowSkeleton(true), 300)
    return () => clearTimeout(t)
  }, [recentQuery.isLoading])

  const doUpload = useCallback(async () => {
    const { file, idempotencyKey } = useUploadDraftStore.getState()
    const hh = useSessionStore.getState().currentHouseholdId
    if (!file || !idempotencyKey || !hh) return
    draft.setUploading()
    try {
      const { receiptId } = await uploadReceipt({
        tempFilePath: file.tempFilePath,
        householdId: hh,
        idempotencyKey,
        onProgress: (p) => draft.setProgress(p),
      })
      draft.setDone()
      draft.clear()
      showToast('小票已上传，正在识别', 'success')
      void goReceipt(receiptId)
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) {
        setError('您没有权限上传到该家庭账本')
        setErrorAction(null)
        draft.setError('您没有权限上传到该家庭账本')
      } else if (e instanceof ApiError && e.status === 400) {
        setError(apiErrorToZh(400))
        setErrorAction('reselect')
        draft.setError(apiErrorToZh(400))
      } else {
        const message = e instanceof ApiError ? e.messageZh : apiErrorToZh(0)
        setError(message)
        setErrorAction('reupload')
        draft.setError(message)
      }
    }
  }, [draft])

  const handlePick = useCallback(
    async (source: 'camera' | 'album') => {
      setError(null)
      setErrorAction(null)
      if (!isOnline) {
        setError('无网络连接，请联网后上传')
        setErrorAction(null)
        return
      }
      const hh = useSessionStore.getState().currentHouseholdId
      if (!hh) {
        void goLogin()
        return
      }
      setLastSource(source)
      let picked
      try {
        picked = await pickImage(source)
      } catch {
        return
      }
      const prepared = await preparePickedImage(picked)
      if (!prepared.ok) {
        setError(IMAGE_ERROR_ZH[prepared.error])
        setErrorAction('reselect')
        return
      }
      draft.setPicked(prepared.file)
      await doUpload()
    },
    [isOnline, draft, doUpload],
  )

  // FAB ở tab khác → mở camera khi trang upload hiện (§4.1).
  const handlePickRef = useRef(handlePick)
  handlePickRef.current = handlePick
  useDidShow(() => {
    if (useUiStore.getState().openCameraOnShow) {
      useUiStore.getState().setOpenCameraOnShow(false)
      void handlePickRef.current('camera')
    }
  })

  usePullDownRefresh(async () => {
    await recentQuery.refetch()
    setJustRefreshed(true)
    Taro.stopPullDownRefresh()
    setTimeout(() => setJustRefreshed(false), 3000)
  })

  const handleBannerAction = () => {
    setError(null)
    if (errorAction === 'reselect') void handlePick(lastSource)
    else if (errorAction === 'reupload') void doUpload()
  }

  const handleSelect = (receipt: Receipt) => {
    void goReceipt(receipt.id)
  }

  const uploading = draft.status === 'uploading'
  const hasPreview = draft.file !== null && (draft.status === 'picked' || uploading)

  return (
    <View style={{ paddingBottom: tokens.size.navHeight + 16 }}>
      <PageHeader title='IMSF-v2' subtitle='拍小票，自动记账入库' />
      <OfflineBanner />
      <View style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>
        {/* Capture card (§5.1): dashed 1.5px accent 60%, radius 16, bg accentContainer 40%. */}
        <View
          style={{
            height: 180,
            borderRadius: tokens.shape.card,
            borderWidth: 1.5,
            borderStyle: 'dashed',
            borderColor: withAlpha(tokens.color.accent, 0.6),
            backgroundColor: withAlpha(tokens.color.accentContainer, 0.4),
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 8,
            padding: 16,
            overflow: 'hidden',
            position: 'relative',
          }}
          onClick={() => void handlePick('camera')}
          aria-label='拍照上传小票'
        >
          {hasPreview && draft.file ? (
            <>
              <Image
                src={draft.file.tempFilePath}
                mode='aspectFill'
                style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%' }}
              />
              <View
                style={{
                  position: 'absolute',
                  top: 8,
                  right: 8,
                  width: 32,
                  height: 32,
                  borderRadius: 16,
                  backgroundColor: withAlpha(tokens.color.onSurface, 0.6),
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
                onClick={(e) => {
                  e.stopPropagation()
                  draft.clear()
                }}
                aria-label='移除图片'
              >
                <Icon name='close' size={18} color={tokens.color.surface} />
              </View>
              {uploading ? (
                <View
                  style={{
                    position: 'absolute',
                    bottom: 0,
                    left: 0,
                    right: 0,
                    padding: 12,
                    backgroundColor: withAlpha(tokens.color.surface, 0.92),
                  }}
                >
                  <Progress value={draft.progress} ariaLabel='正在上传' />
                  <Text style={{ fontSize: 13, color: tokens.color.onSurfaceVariant, marginTop: 6 }}>
                    正在上传… {draft.progress}%
                  </Text>
                </View>
              ) : null}
            </>
          ) : (
            <>
              <Icon name='camera' size={48} color={tokens.color.accent} />
              <Text style={{ fontSize: 16, fontWeight: 600, color: tokens.color.onSurface }}>点击拍照</Text>
              <Text style={{ fontSize: 13, color: tokens.color.onSurfaceVariant }}>
                支持中文 / 越南文小票 · JPG、PNG、WebP
              </Text>
              <Text style={{ fontSize: 12, color: tokens.color.onSurfaceVariant }}>
                单张不超过 10 MB · 请拍清小票全貌
              </Text>
            </>
          )}
        </View>

        {/* Lỗi inline dưới card (⚠ + text + 重新选择/重新上传) — KHÔNG dùng toast (§5.1). */}
        {error ? (
          <View
            style={{
              backgroundColor: tokens.color.errorContainer,
              borderRadius: tokens.shape.base,
              padding: 12,
              display: 'flex',
              flexDirection: 'row',
              alignItems: 'center',
              gap: 8,
            }}
          >
            <Icon name='warning' size={16} color={tokens.color.error} />
            <Text style={{ fontSize: 13, color: tokens.color.error, flex: 1 }}>{error}</Text>
            {errorAction ? (
              <Text
                style={{ fontSize: 13, fontWeight: 600, color: tokens.color.accent }}
                onClick={handleBannerAction}
              >
                {errorAction === 'reselect' ? '重新选择' : '重新上传'}
              </Text>
            ) : null}
          </View>
        ) : null}

        <View style={{ display: 'flex', flexDirection: 'row', gap: 12 }}>
          <View style={{ flex: 1 }}>
            <Button variant='primary' size='large' block onClick={() => void handlePick('camera')} disabled={uploading}>
              拍照
            </Button>
          </View>
          <View style={{ flex: 1 }}>
            <Button variant='outline' size='large' block onClick={() => void handlePick('album')} disabled={uploading}>
              从相册选择
            </Button>
          </View>
        </View>

        <View>
          <View
            style={{
              display: 'flex',
              flexDirection: 'row',
              alignItems: 'center',
              justifyContent: 'space-between',
              paddingTop: 8,
              paddingBottom: 4,
            }}
          >
            <View style={{ display: 'flex', flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Text style={{ fontSize: 16, fontWeight: 600, color: tokens.color.onSurface }}>最近小票</Text>
              {justRefreshed ? (
                <Text style={{ fontSize: 12, color: tokens.color.accent }}>已更新</Text>
              ) : null}
            </View>
            <Text
              style={{ fontSize: 14, color: tokens.color.accent }}
              onClick={() => void goReceipts()}
            >
              查看全部 ›
            </Text>
          </View>
          {!householdId ? (
            <View
              style={{
                backgroundColor: tokens.color.surface,
                borderRadius: tokens.shape.base,
                padding: 16,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'flex-start',
                gap: 8,
              }}
            >
              <Text style={{ fontSize: 14, color: tokens.color.onSurface }}>请先登录</Text>
              <Text style={{ fontSize: 13, color: tokens.color.onSurfaceVariant }}>
                登录后即可查看最近小票
              </Text>
              <Button variant='primary' onClick={() => void goLogin()}>
                去登录
              </Button>
            </View>
          ) : (
            <ReceiptList
              receipts={recentQuery.data ?? []}
              isLoading={recentQuery.isLoading}
              showSkeleton={showSkeleton}
              isError={recentQuery.isError}
              onRetry={() => void recentQuery.refetch()}
              onSelect={handleSelect}
              limit={3}
              emptyState={
                <EmptyState
                  icon='camera'
                  title='还没有小票'
                  body='拍下第一张小票，自动记账并同步到冰箱。'
                  actionLabel='立即拍照'
                  onAction={() => void handlePick('camera')}
                />
              }
            />
          )}
        </View>
      </View>
      <TabBarHost />
    </View>
  )
}
