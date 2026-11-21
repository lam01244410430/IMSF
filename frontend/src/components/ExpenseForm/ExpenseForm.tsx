/**
 * Form nhập chi tay — FE-03 (design doc §6 hàng 4): amount, currency
 * (CNY/VND — chỉ hai tiền tệ backend chấp nhận, D-F7), category (4 giá trị
 * backend), date (occurred_at, mặc định hôm nay), note (khoản gì).
 * Submit → POST /api/v2/transactions với type='expense' (income không lộ
 * ra ở form sổ chi tiêu). Thành công → toast 已记账 + invalidate list/summary.
 *
 * Validation client-side trước, server là thẩm quyền (amount Decimal gt=0,
 * currency/category sai → 422, map qua ApiError.messageZh).
 * Số tiền chuẩn hoá khi submit bằng normalizeAmountInput (TextField primitive
 * không có prop onBlur nên không chuẩn hoá được khi blur — giá trị gửi lên
 * và hiển thị sau đó vẫn là dạng đã chuẩn hoá qua formatAmount).
 */
import { useEffect, useState } from 'react'
import { Picker as TaroPicker, Text, View } from '@tarojs/components'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import Button from '../../ui/primitives/Button'
import Icon from '../../ui/primitives/Icon'
import SelectPicker from '../../ui/primitives/Picker'
import TextField from '../../ui/primitives/TextField'
import { showToast } from '../../ui/primitives/Toast'
import { tokens } from '../../ui/tokens'
import { ApiError } from '../../services/errors'
import {
  CATEGORY_LABELS,
  CURRENCY_LABELS,
  TRANSACTION_CATEGORIES,
  TRANSACTION_CURRENCIES,
  createTransaction,
  validateAmountText,
  type Transaction,
  type TransactionCategory,
} from '../../services/transactions'
import type { Currency } from '../../utils/format'
import { dateToOccurredAt, normalizeAmountInput, todayDate } from '../../utils/format'

export interface ExpenseFormProps {
  householdId: string
  defaultCurrency: Currency
  timezone?: string
  onCreated?: (tx: Transaction) => void
}

const CURRENCY_OPTIONS = TRANSACTION_CURRENCIES.map((c) => ({
  label: `${CURRENCY_LABELS[c]} ${c === 'CNY' ? '¥' : '₫'}`,
  value: c,
}))

const CATEGORY_OPTIONS = TRANSACTION_CATEGORIES.map((c) => ({
  label: CATEGORY_LABELS[c],
  value: c,
}))

function SelectRow({
  label,
  value,
  error,
  onClick,
}: {
  label: string
  value: string
  error?: string
  onClick: () => void
}) {
  return (
    <View style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <Text style={{ fontSize: 14, color: tokens.color.onSurfaceVariant }}>{label}</Text>
      <View
        style={{
          height: tokens.size.textFieldHeight,
          borderWidth: 1,
          borderStyle: 'solid',
          borderColor: error ? tokens.color.error : tokens.color.outline,
          borderRadius: 12,
          paddingLeft: 16,
          paddingRight: 16,
          display: 'flex',
          flexDirection: 'row',
          alignItems: 'center',
          justifyContent: 'space-between',
          backgroundColor: tokens.color.surface,
        }}
        onClick={onClick}
      >
        <Text style={{ fontSize: 16, color: tokens.color.onSurface }}>{value}</Text>
        <Icon name='chevron-down' size={16} color={tokens.color.onSurfaceVariant} />
      </View>
      {error ? (
        <Text style={{ fontSize: 12, color: tokens.color.error }}>{error}</Text>
      ) : null}
    </View>
  )
}

export default function ExpenseForm({ householdId, defaultCurrency, timezone, onCreated }: ExpenseFormProps) {
  const tz = timezone ?? 'Asia/Shanghai'
  const queryClient = useQueryClient()
  const [amountText, setAmountText] = useState('')
  const [currency, setCurrency] = useState<Currency>(defaultCurrency)
  const [currencyTouched, setCurrencyTouched] = useState(false)
  // defaultCurrency đến từ GET /households (load async) — đồng bộ lại khi
  // prop đổi, trừ khi user đã tự chọn tiền tệ.
  useEffect(() => {
    if (!currencyTouched) setCurrency(defaultCurrency)
  }, [defaultCurrency, currencyTouched])
  const [category, setCategory] = useState<TransactionCategory>('food')
  const [date, setDate] = useState(todayDate(tz))
  const [note, setNote] = useState('')
  const [amountError, setAmountError] = useState<string | undefined>(undefined)
  const [dateError, setDateError] = useState<string | undefined>(undefined)
  const [currencyPickerVisible, setCurrencyPickerVisible] = useState(false)
  const [categoryPickerVisible, setCategoryPickerVisible] = useState(false)

  const mutation = useMutation({
    mutationFn: () =>
      createTransaction({
        household_id: householdId,
        type: 'expense',
        amount: Number(normalizeAmountInput(amountText)),
        currency,
        category,
        occurred_at: dateToOccurredAt(date, tz),
        note: note.trim() || undefined,
      }),
    onSuccess: (tx) => {
      void queryClient.invalidateQueries({ queryKey: ['transactions', householdId] })
      void queryClient.invalidateQueries({ queryKey: ['spending-summary', householdId] })
      showToast('已记账', 'success')
      setAmountText('')
      setNote('')
      setAmountError(undefined)
      setDateError(undefined)
      onCreated?.(tx)
    },
    onError: (e: unknown) => {
      showToast(e instanceof ApiError ? e.messageZh : '服务器开小差了，请稍后重试', 'error')
    },
  })

  const handleSubmit = () => {
    const amountErr = validateAmountText(amountText)
    const dateErr = date ? undefined : '请选择日期'
    setAmountError(amountErr ?? undefined)
    setDateError(dateErr)
    if (amountErr || dateErr) return
    mutation.mutate()
  }

  return (
    <View
      style={{
        backgroundColor: tokens.color.surface,
        borderRadius: 16,
        padding: 16,
        display: 'flex',
        flexDirection: 'column',
        gap: 12,
      }}
    >
      <TextField
        label='金额'
        value={amountText}
        onChange={(v) => {
          setAmountText(v)
          if (amountError) setAmountError(undefined)
        }}
        type='number'
        inputMode='decimal'
        placeholder='请输入金额'
        error={amountError}
      />
      <SelectRow
        label='货币'
        value={`${CURRENCY_LABELS[currency]} ${currency === 'CNY' ? '¥' : '₫'}`}
        onClick={() => setCurrencyPickerVisible(true)}
      />
      <SelectRow
        label='分类'
        value={CATEGORY_LABELS[category]}
        onClick={() => setCategoryPickerVisible(true)}
      />
      <View style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <Text style={{ fontSize: 14, color: tokens.color.onSurfaceVariant }}>日期</Text>
        <TaroPicker mode='date' value={date} onChange={(e) => setDate(String(e.detail.value))}>
          <View
            style={{
              height: tokens.size.textFieldHeight,
              borderWidth: 1,
              borderStyle: 'solid',
              borderColor: dateError ? tokens.color.error : tokens.color.outline,
              borderRadius: 12,
              paddingLeft: 16,
              paddingRight: 16,
              display: 'flex',
              flexDirection: 'row',
              alignItems: 'center',
              justifyContent: 'space-between',
              backgroundColor: tokens.color.surface,
            }}
          >
            <Text style={{ fontSize: 16, color: tokens.color.onSurface }}>{date || '请选择日期'}</Text>
            <Icon name='chevron-down' size={16} color={tokens.color.onSurfaceVariant} />
          </View>
        </TaroPicker>
        {dateError ? (
          <Text style={{ fontSize: 12, color: tokens.color.error }}>{dateError}</Text>
        ) : null}
      </View>
      <TextField label='备注' value={note} onChange={setNote} placeholder='比如：午饭' maxLength={100} />
      <Button variant='primary' block loading={mutation.isPending} onClick={handleSubmit}>
        记一笔
      </Button>
      <SelectPicker
        visible={currencyPickerVisible}
        title='选择货币'
        options={CURRENCY_OPTIONS}
        value={currency}
        onConfirm={(v) => {
          setCurrency(v as Currency)
          setCurrencyTouched(true)
          setCurrencyPickerVisible(false)
        }}
        onCancel={() => setCurrencyPickerVisible(false)}
      />
      <SelectPicker
        visible={categoryPickerVisible}
        title='选择分类'
        options={CATEGORY_OPTIONS}
        value={category}
        onConfirm={(v) => {
          setCategory(v as TransactionCategory)
          setCategoryPickerVisible(false)
        }}
        onCancel={() => setCategoryPickerVisible(false)}
      />
    </View>
  )
}
