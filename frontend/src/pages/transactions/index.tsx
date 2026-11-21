/**
 * 记账 — sổ chi tiêu thủ công (FE-03, design doc §6 hàng 4):
 * form nhập chi tay (ExpenseForm) + danh sách giao dịch của nhà, mới nhất trước.
 *
 * - Chỉ chi tay (receipt_id null) mới sửa/xoá được — mở dialog sửa; chi từ
 *   hoá đơn hiện chip 「小票」, chỉ đọc, không có nút sửa/xoá (PATCH/DELETE
 *   sẽ 409 — UI không bao giờ hiện nút bấm rồi 409).
 * - Số tiền hiển thị bằng formatAmount (bỏ số 0 thừa: ¥100 thay vì ¥100.00).
 * - Không bao giờ cộng trộn tiền tệ: mỗi dòng hiện ký hiệu của chính nó.
 */
import { useEffect, useState } from 'react'
import { Picker as TaroPicker, Text, View } from '@tarojs/components'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import PageHeader from '../../components/PageHeader/PageHeader'
import OfflineBanner from '../../components/OfflineBanner/OfflineBanner'
import EmptyState from '../../components/EmptyState/EmptyState'
import ExpenseForm from '../../components/ExpenseForm/ExpenseForm'
import Button from '../../ui/primitives/Button'
import Dialog, { confirmDialog } from '../../ui/primitives/Dialog'
import Icon from '../../ui/primitives/Icon'
import ListRow from '../../ui/primitives/ListRow'
import SelectPicker from '../../ui/primitives/Picker'
import Skeleton from '../../ui/primitives/Skeleton'
import TextField from '../../ui/primitives/TextField'
import { showToast } from '../../ui/primitives/Toast'
import { tokens } from '../../ui/tokens'
import { ApiError } from '../../services/errors'
import {
  CATEGORY_LABELS,
  TYPE_LABELS,
  deleteTransaction,
  isManualTransaction,
  listTransactions,
  patchTransaction,
  validateAmountText,
  type Transaction,
  type TransactionCategory,
} from '../../services/transactions'
import { goBack, goLogin, goSpending } from '../../config/routes'
import { useSessionStore } from '../../store/session'
import { listHouseholds } from '../../services/households'
import type { Currency } from '../../utils/format'
import {
  dateToOccurredAt,
  formatAmount,
  formatRelativeDate,
  normalizeAmountInput,
  occurredAtToDate,
} from '../../utils/format'

type CurrencyFilter = 'all' | Currency

const CURRENCY_FILTERS: { key: CurrencyFilter; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'CNY', label: '人民币 ¥' },
  { key: 'VND', label: '越南盾 ₫' },
]

function ReceiptChip() {
  return (
    <View
      style={{
        backgroundColor: tokens.color.accentContainer,
        borderRadius: 8,
        paddingTop: 2,
        paddingBottom: 2,
        paddingLeft: 8,
        paddingRight: 8,
      }}
    >
      <Text style={{ fontSize: 12, fontWeight: 500, color: tokens.color.onAccentContainer }}>小票</Text>
    </View>
  )
}

export default function Transactions() {
  const householdId = useSessionStore((s) => s.currentHouseholdId)
  const isLoggedIn = useSessionStore((s) => s.isLoggedIn)
  const queryClient = useQueryClient()
  // default_currency/timezone lấy từ GET /households (đầy đủ field) — session
  // store chỉ giữ HouseholdSummary {id, name} (xem services/auth.ts).
  const householdsQuery = useQuery({
    queryKey: ['households'],
    queryFn: () => listHouseholds(),
    enabled: isLoggedIn,
  })
  const currentHousehold = householdsQuery.data?.find((h) => h.id === householdId)
  const defaultCurrency: Currency =
    currentHousehold?.default_currency === 'VND' ? 'VND' : 'CNY'
  const timezone = currentHousehold?.timezone ?? 'Asia/Shanghai'

  const [currencyFilter, setCurrencyFilter] = useState<CurrencyFilter>('all')
  const [editing, setEditing] = useState<Transaction | null>(null)
  const [editAmount, setEditAmount] = useState('')
  const [editCategory, setEditCategory] = useState<TransactionCategory>('food')
  const [editDate, setEditDate] = useState('')
  const [editNote, setEditNote] = useState('')
  const [editAmountError, setEditAmountError] = useState<string | undefined>(undefined)
  const [categoryPickerVisible, setCategoryPickerVisible] = useState(false)

  const query = useQuery({
    queryKey: ['transactions', householdId, currencyFilter],
    queryFn: () =>
      listTransactions(householdId as string, {
        currency: currencyFilter === 'all' ? undefined : currencyFilter,
        limit: 50,
      }),
    enabled: Boolean(householdId),
  })

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

  const patchMutation = useMutation({
    mutationFn: () =>
      patchTransaction((editing as Transaction).id, {
        amount: Number(normalizeAmountInput(editAmount)),
        category: editCategory,
        note: editNote.trim() || null,
        occurred_at: dateToOccurredAt(editDate, timezone),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['transactions', householdId] })
      void queryClient.invalidateQueries({ queryKey: ['spending-summary', householdId] })
      showToast('已保存', 'success')
      setEditing(null)
    },
    onError: (e: unknown) => {
      showToast(e instanceof ApiError ? e.messageZh : '服务器开小差了，请稍后重试', 'error')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: () => deleteTransaction((editing as Transaction).id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['transactions', householdId] })
      void queryClient.invalidateQueries({ queryKey: ['spending-summary', householdId] })
      showToast('已删除', 'success')
      setEditing(null)
    },
    onError: (e: unknown) => {
      showToast(e instanceof ApiError ? e.messageZh : '服务器开小差了，请稍后重试', 'error')
    },
  })

  const openEdit = (tx: Transaction) => {
    setEditing(tx)
    setEditAmount(String(tx.amount))
    setEditCategory(tx.category)
    setEditDate(occurredAtToDate(tx.occurred_at, timezone))
    setEditNote(tx.note ?? '')
    setEditAmountError(undefined)
  }

  const handleSaveEdit = () => {
    const err = validateAmountText(editAmount)
    setEditAmountError(err ?? undefined)
    if (err || !editDate) return
    patchMutation.mutate()
  }

  const handleDelete = async () => {
    const ok = await confirmDialog({
      title: '删除这笔记账？',
      content: '删除后无法恢复。',
      confirmText: '删除',
      cancelText: '取消',
    })
    if (ok) deleteMutation.mutate()
  }

  const transactions = query.data ?? []

  return (
    <View>
      <PageHeader title='记账' subtitle='手动记录每一笔支出' showBack onBack={() => void goBack()} />
      <OfflineBanner />
      <View style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>
        {!isLoggedIn || !householdId ? (
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
            <Text style={{ fontSize: 13, color: tokens.color.onSurfaceVariant }}>登录后即可使用全部功能</Text>
            <Button variant='primary' onClick={() => void goLogin()}>
              去登录
            </Button>
          </View>
        ) : (
          <>
            <ExpenseForm householdId={householdId} defaultCurrency={defaultCurrency} timezone={timezone} />
            <View
              style={{
                display: 'flex',
                flexDirection: 'row',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <Text style={{ fontSize: 16, fontWeight: 600, color: tokens.color.onSurface }}>最近记账</Text>
              <Button variant='ghost' onClick={() => void goSpending()}>
                消费统计 ›
              </Button>
            </View>
            <View style={{ display: 'flex', flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
              {CURRENCY_FILTERS.map((f) => (
                <Button
                  key={f.key}
                  size='small'
                  variant={currencyFilter === f.key ? 'primary' : 'outline'}
                  onClick={() => setCurrencyFilter(f.key)}
                >
                  {f.label}
                </Button>
              ))}
            </View>
            {query.isLoading && showSkeleton ? (
              <Skeleton rows={5} />
            ) : query.isError ? (
              <View
                style={{
                  backgroundColor: tokens.color.surface,
                  borderRadius: 16,
                  padding: 24,
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: 12,
                }}
              >
                <Text style={{ fontSize: 14, color: tokens.color.onSurface }}>加载失败，请检查网络后重试</Text>
                <Button variant='outline' onClick={() => void query.refetch()}>
                  重试
                </Button>
              </View>
            ) : transactions.length === 0 ? (
              <EmptyState
                icon='info'
                title='还没有记账'
                body='记下第一笔支出，月底可以在消费统计里查看汇总。'
              />
            ) : (
              <View style={{ backgroundColor: tokens.color.surface, borderRadius: 16 }}>
                {transactions.map((tx) => {
                  const manual = isManualTransaction(tx)
                  return (
                    <ListRow
                      key={tx.id}
                      title={tx.note?.trim() ? tx.note : CATEGORY_LABELS[tx.category]}
                      subtitle={`${formatRelativeDate(tx.occurred_at, timezone)} · ${CATEGORY_LABELS[tx.category]} · ${TYPE_LABELS[tx.type]}${manual ? '' : ' · 来自小票'}`}
                      amount={formatAmount(tx.amount, tx.currency)}
                      chip={
                        manual ? (
                          <Icon name='chevron-right' size={16} color={tokens.color.onSurfaceVariant} />
                        ) : (
                          <ReceiptChip />
                        )
                      }
                      onClick={manual ? () => openEdit(tx) : undefined}
                    />
                  )
                })}
              </View>
            )}
          </>
        )}
      </View>
      <Dialog
        open={editing !== null}
        title='编辑记账'
        confirmText='保存'
        cancelText='取消'
        onConfirm={handleSaveEdit}
        onCancel={() => setEditing(null)}
        content={
          editing ? (
            <View style={{ display: 'flex', flexDirection: 'column', gap: 12, paddingTop: 8 }}>
              <TextField
                label='金额'
                value={editAmount}
                onChange={(v) => {
                  setEditAmount(v)
                  if (editAmountError) setEditAmountError(undefined)
                }}
                type='number'
                inputMode='decimal'
                placeholder='请输入金额'
                error={editAmountError}
              />
              <View style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <Text style={{ fontSize: 14, color: tokens.color.onSurfaceVariant }}>分类</Text>
                <View
                  style={{
                    height: tokens.size.textFieldHeight,
                    borderWidth: 1,
                    borderStyle: 'solid',
                    borderColor: tokens.color.outline,
                    borderRadius: 12,
                    paddingLeft: 16,
                    paddingRight: 16,
                    display: 'flex',
                    flexDirection: 'row',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    backgroundColor: tokens.color.surface,
                  }}
                  onClick={() => setCategoryPickerVisible(true)}
                >
                  <Text style={{ fontSize: 16, color: tokens.color.onSurface }}>{CATEGORY_LABELS[editCategory]}</Text>
                  <Icon name='chevron-down' size={16} color={tokens.color.onSurfaceVariant} />
                </View>
              </View>
              <View style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <Text style={{ fontSize: 14, color: tokens.color.onSurfaceVariant }}>日期</Text>
                <TaroPicker mode='date' value={editDate} onChange={(e) => setEditDate(String(e.detail.value))}>
                  <View
                    style={{
                      height: tokens.size.textFieldHeight,
                      borderWidth: 1,
                      borderStyle: 'solid',
                      borderColor: tokens.color.outline,
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
                    <Text style={{ fontSize: 16, color: tokens.color.onSurface }}>{editDate || '请选择日期'}</Text>
                    <Icon name='chevron-down' size={16} color={tokens.color.onSurfaceVariant} />
                  </View>
                </TaroPicker>
              </View>
              <TextField label='备注' value={editNote} onChange={setEditNote} placeholder='比如：午饭' maxLength={100} />
              <Button variant='danger' block loading={deleteMutation.isPending} onClick={() => void handleDelete()}>
                删除这笔记账
              </Button>
              <SelectPicker
                visible={categoryPickerVisible}
                title='选择分类'
                options={Object.entries(CATEGORY_LABELS).map(([value, label]) => ({ label, value }))}
                value={editCategory}
                onConfirm={(v) => {
                  setEditCategory(v as TransactionCategory)
                  setCategoryPickerVisible(false)
                }}
                onCancel={() => setCategoryPickerVisible(false)}
              />
            </View>
          ) : null
        }
      />
    </View>
  )
}
