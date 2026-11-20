/**
 * LineCard — một dòng sửa được của Màn 03 (§5.3): 数量 / 单位 (picker) /
 * 单价 ¥ / 小计 tự cập nhật + chip canonical_name (hoặc 未匹配 + input gõ
 * tên chuẩn) + toggle 记入冰箱库存 + 删除此行.
 *
 * TextField là controlled (value string) nên card giữ string local cho 3 ô
 * text — tránh hiện "NaN" / mất dấu "." khi user đang gõ; số parse được
 * ghi vào draft (live summary) ngay mỗi lần gõ, số không parse được tính 0.
 */
import { useEffect, useRef, useState } from 'react'
import { Text, View } from '@tarojs/components'
import TextField from '../../ui/primitives/TextField'
import Picker from '../../ui/primitives/Picker'
import Switch from '../../ui/primitives/Switch'
import { tokens } from '../../ui/tokens'
import {
  draftLineTotal,
  useReviewDraftStore,
  type ReviewLineDraft,
} from '../../store/reviewDraft'
import { formatMoney } from '../../utils/format'

export interface LineFieldErrors {
  quantity?: string
  unitPrice?: string
  rawName?: string
  unit?: string
}

export const UNIT_OPTIONS = ['个', '盒', '瓶', '袋', '千克', '克', '升', '毫升'].map((u) => ({
  label: u,
  value: u,
}))

function hasMoreThan2Decimals(n: number): boolean {
  return Math.abs(n * 100 - Math.round(n * 100)) > 1e-6
}

/** Validation client-side (§5.3) — chạy trên string user gõ, không phải số đã parse. */
export function validateLineTexts(
  draft: ReviewLineDraft,
  qtyText: string,
  priceText: string,
  nameText: string,
): LineFieldErrors {
  const errors: LineFieldErrors = {}
  const qty = Number.parseFloat(qtyText)
  if (!Number.isFinite(qty) || qty <= 0) errors.quantity = '数量必须大于 0'
  const price = Number.parseFloat(priceText)
  if (!Number.isFinite(price)) {
    errors.unitPrice = '请输入金额'
  } else if (hasMoreThan2Decimals(price)) {
    errors.unitPrice = '金额最多保留两位小数'
  } else if (draft.isDiscount && price > 0) {
    errors.unitPrice = '优惠金额不能为正数'
  } else if (!draft.isDiscount && price < 0) {
    errors.unitPrice = '金额不能为负数'
  }
  if (!draft.unit) errors.unit = '请选择单位'
  if (draft.isNew && !nameText.trim()) errors.rawName = '请填写商品名称'
  return errors
}

export interface LineCardProps {
  draft: ReviewLineDraft
  currency: string
  /** Lỗi hiện inline — parent bật sau lần bấm confirm đầu (submitted). */
  forceShowErrors: boolean
  errors: LineFieldErrors
  onErrorsChange: (clientKey: string, errors: LineFieldErrors) => void
  onRemove: (clientKey: string) => void
  canRemove: boolean
}

export default function LineCard(props: LineCardProps) {
  const { draft, currency, forceShowErrors, errors, onErrorsChange, onRemove, canRemove } = props
  const updateLine = useReviewDraftStore((s) => s.updateLine)
  const [qtyText, setQtyText] = useState(() => String(draft.quantity))
  const [priceText, setPriceText] = useState(() => String(draft.unitPrice))
  const [nameText, setNameText] = useState(() => draft.rawName)
  const [canonicalText, setCanonicalText] = useState(() => draft.canonicalName ?? '')
  const [canonicalEditing, setCanonicalEditing] = useState(false)
  const [pickerVisible, setPickerVisible] = useState(false)
  const [touched, setTouched] = useState({ qty: false, price: false, name: false })

  const computed = validateLineTexts(draft, qtyText, priceText, nameText)
  const sig = JSON.stringify(computed)
  const prevSig = useRef('')
  useEffect(() => {
    if (sig !== prevSig.current) {
      prevSig.current = sig
      onErrorsChange(draft.clientKey, computed)
    }
  }, [sig, draft.clientKey, onErrorsChange, computed])

  const showQtyError = forceShowErrors || touched.qty
  const showPriceError = forceShowErrors || touched.price
  const showNameError = forceShowErrors || touched.name

  const handleQtyChange = (v: string) => {
    setQtyText(v)
    setTouched((t) => ({ ...t, qty: true }))
    const n = Number.parseFloat(v)
    updateLine(draft.clientKey, { quantity: Number.isFinite(n) ? n : 0 })
  }
  const handlePriceChange = (v: string) => {
    setPriceText(v)
    setTouched((t) => ({ ...t, price: true }))
    const n = Number.parseFloat(v)
    updateLine(draft.clientKey, { unitPrice: Number.isFinite(n) ? n : 0 })
  }
  const handleNameChange = (v: string) => {
    setNameText(v)
    setTouched((t) => ({ ...t, name: true }))
    updateLine(draft.clientKey, { rawName: v })
  }

  const feeTag = /运费|服务费/.test(draft.rawName) ? '费用' : '优惠'
  const displayCurrency = currency === 'VND' ? 'VND' : 'CNY'

  return (
    <View
      id={`line-${draft.clientKey}`}
      style={{
        backgroundColor: tokens.color.surface,
        borderRadius: tokens.shape.base,
        padding: 12,
        display: 'flex',
        flexDirection: 'column',
        gap: 12,
        borderLeftWidth: draft.isDiscount ? 3 : 0,
        borderLeftStyle: 'solid',
        borderLeftColor: tokens.color.secondary,
      }}
    >
      {/* Header: line_no + raw_name + chip canonical / 未匹配 */}
      <View style={{ display: 'flex', flexDirection: 'row', alignItems: 'flex-start', gap: 8 }}>
        <Text style={{ fontSize: 13, color: tokens.color.onSurfaceVariant, marginTop: 2 }}>
          {draft.lineNo}.
        </Text>
        <View style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 4 }}>
          {draft.isNew ? (
            <TextField
              label='商品名称'
              value={nameText}
              onChange={handleNameChange}
              placeholder='输入商品名称'
              error={showNameError ? errors.rawName : undefined}
            />
          ) : (
            <Text style={{ fontSize: 15, fontWeight: 600, color: tokens.color.onSurface }}>
              {draft.rawName}
            </Text>
          )}
          {draft.isDiscount ? (
            <View
              style={{
                alignSelf: 'flex-start',
                backgroundColor: tokens.color.secondaryContainer,
                borderRadius: 12,
                paddingLeft: 8,
                paddingRight: 8,
                height: 24,
                display: 'flex',
                alignItems: 'center',
              }}
            >
              <Text style={{ fontSize: 12, color: tokens.color.secondary }}>{feeTag}</Text>
            </View>
          ) : null}
        </View>
        {draft.isDiscount ? null : draft.canonicalName ? (
          <View
            style={{
              backgroundColor: tokens.color.primaryContainer,
              borderRadius: 12,
              paddingLeft: 8,
              paddingRight: 8,
              height: 24,
              display: 'flex',
              alignItems: 'center',
            }}
          >
            <Text style={{ fontSize: 13, color: tokens.color.onPrimaryContainer }}>
              {draft.canonicalName}
            </Text>
          </View>
        ) : canonicalEditing ? (
          <View style={{ width: 140 }}>
            <TextField
              label='标准名称'
              value={canonicalText}
              onChange={(v) => {
                setCanonicalText(v)
                updateLine(draft.clientKey, { canonicalName: v.trim() ? v.trim() : null })
              }}
              placeholder='输入标准食材名称'
            />
          </View>
        ) : (
          <View
            style={{
              backgroundColor: tokens.color.warningContainer,
              borderRadius: 12,
              paddingLeft: 8,
              paddingRight: 8,
              height: 24,
              display: 'flex',
              alignItems: 'center',
            }}
            onClick={() => setCanonicalEditing(true)}
          >
            <Text style={{ fontSize: 13, color: tokens.color.warning }}>未匹配</Text>
          </View>
        )}
      </View>

      {/* Dòng field sửa được: 数量 / 单位 / 单价 ¥ / 小计 */}
      <View style={{ display: 'flex', flexDirection: 'row', alignItems: 'flex-start', gap: 8 }}>
        <View style={{ width: 56 }}>
          <TextField
            label='数量'
            value={qtyText}
            onChange={handleQtyChange}
            type='number'
            inputMode='decimal'
            error={showQtyError ? errors.quantity : undefined}
          />
        </View>
        <View style={{ width: 72, display: 'flex', flexDirection: 'column', gap: 4 }}>
          <Text style={{ fontSize: 12, color: tokens.color.onSurfaceVariant }}>单位</Text>
          <View
            style={{
              height: 40,
              borderWidth: 1,
              borderStyle: 'solid',
              borderColor: errors.unit && forceShowErrors ? tokens.color.error : tokens.color.outline,
              borderRadius: tokens.shape.textField,
              display: 'flex',
              flexDirection: 'row',
              alignItems: 'center',
              justifyContent: 'space-between',
              paddingLeft: 8,
              paddingRight: 8,
            }}
            onClick={() => setPickerVisible(true)}
          >
            <Text style={{ fontSize: 14, color: tokens.color.onSurface }}>{draft.unit || '—'}</Text>
            <Text style={{ fontSize: 12, color: tokens.color.onSurfaceVariant }}>▾</Text>
          </View>
          {errors.unit && forceShowErrors ? (
            <Text style={{ fontSize: 12, color: tokens.color.error }}>⚠ {errors.unit}</Text>
          ) : null}
        </View>
        <View style={{ width: 80 }}>
          <TextField
            label='单价 ¥'
            value={priceText}
            onChange={handlePriceChange}
            type='number'
            inputMode='decimal'
            error={showPriceError ? errors.unitPrice : undefined}
          />
        </View>
        <View
          style={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'flex-end',
            gap: 4,
            paddingTop: 2,
          }}
        >
          <Text style={{ fontSize: 12, color: tokens.color.onSurfaceVariant }}>小计</Text>
          <Text style={{ fontSize: 15, fontWeight: 600, color: tokens.color.onSurface }}>
            {formatMoney(draftLineTotal(draft), displayCurrency)}
          </Text>
        </View>
      </View>

      {/* Toggle is_stock_item — ẩn với dòng giảm giá/phí (§5.3) */}
      {draft.isDiscount ? null : (
        <View style={{ display: 'flex', flexDirection: 'row', alignItems: 'center', gap: 12 }}>
          <Switch
            checked={draft.isStockItem}
            onChange={(checked) => updateLine(draft.clientKey, { isStockItem: checked })}
            ariaLabel='记入冰箱库存'
          />
          <View style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <Text style={{ fontSize: 14, color: tokens.color.onSurface }}>记入冰箱库存</Text>
            <Text style={{ fontSize: 13, color: tokens.color.onSurfaceVariant }}>关闭后只记账，不入库。</Text>
          </View>
        </View>
      )}

      {/* Xóa dòng */}
      <View style={{ display: 'flex', flexDirection: 'row', justifyContent: 'flex-end' }}>
        <Text
          style={{
            fontSize: 14,
            color: canRemove ? tokens.color.error : tokens.color.textDisabled,
            paddingTop: 10,
            paddingBottom: 10,
            paddingLeft: 12,
            paddingRight: 12,
            minHeight: 44,
          }}
          onClick={() => onRemove(draft.clientKey)}
        >
          删除此行
        </Text>
      </View>

      <Picker
        visible={pickerVisible}
        title='选择单位'
        options={UNIT_OPTIONS}
        value={draft.unit || null}
        onConfirm={(v) => {
          updateLine(draft.clientKey, { unit: String(v) })
          setPickerVisible(false)
        }}
        onCancel={() => setPickerVisible(false)}
      />
    </View>
  )
}
