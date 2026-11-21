/**
 * Expense book (/app/transactions) — the priority feature.
 *
 * Desktop: sticky 360px entry form panel + a real table
 * (日期 / 分类 / 金额 / 备注 / 类型 / 操作). Mobile: the form sits above
 * the list. Form: amount, currency (14 — default = the household's
 * default_currency, else CNY), category, date (default today in the
 * household timezone), note; submit → POST /transactions with
 * type='expense'. List newest-first.
 *
 * Edit (dialog → PATCH) and Delete (confirm → DELETE) exist ONLY for
 * manual rows (receipt_id null). Receipt-linked rows show a 小票 chip +
 * 来自小票 and are read-only (the backend returns 409 for PATCH/DELETE
 * on them, so the UI offers no buttons). Amounts render with
 * formatAmount — redundant trailing zeros stripped.
 */
import { useCallback, useEffect, useState, type FormEvent } from 'react'
import {
  CATEGORY_LABELS,
  createTransaction,
  deleteTransaction,
  isManualTransaction,
  listTransactions,
  patchTransaction,
  TRANSACTION_CATEGORIES,
  type Transaction,
  type TransactionCategory,
} from '../../lib/api'
import { useCurrentHousehold } from '../../lib/household'
import {
  CURRENCY_LABELS,
  dateToOccurredAt,
  formatAmount,
  formatRelativeDate,
  normalizeAmountInput,
  occurredAtToDate,
  resolveCurrency,
  SUPPORTED_CURRENCIES,
  todayDate,
  validateAmountText,
  type Currency,
} from '../../lib/format'
import { StatusChip } from '../../components/StatusChip'

interface FormState {
  amount: string
  currency: Currency
  category: TransactionCategory
  date: string
  note: string
}

export function buildCreatePayload(
  form: FormState,
  householdId: string,
  timezone: string,
): {
  household_id: string
  type: 'expense'
  amount: number
  currency: Currency
  category: TransactionCategory
  occurred_at: string
  note?: string
} {
  const payload: {
    household_id: string
    type: 'expense'
    amount: number
    currency: Currency
    category: TransactionCategory
    occurred_at: string
    note?: string
  } = {
    household_id: householdId,
    type: 'expense',
    amount: Number(normalizeAmountInput(form.amount)),
    currency: form.currency,
    category: form.category,
    occurred_at: dateToOccurredAt(form.date, timezone),
  }
  const note = form.note.trim()
  if (note) payload.note = note
  return payload
}

export function TransactionsPage() {
  const { household, defaultCurrency, timezone, loading: householdLoading, error: householdError } =
    useCurrentHousehold()
  const [rows, setRows] = useState<Transaction[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [formError, setFormError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [editing, setEditing] = useState<Transaction | null>(null)
  const [editForm, setEditForm] = useState<FormState | null>(null)
  const [editError, setEditError] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [pendingDelete, setPendingDelete] = useState<Transaction | null>(null)

  // Escape closes either dialog (Phase 4, F-08) -- same pattern as
  // the landing drawer / notifications panel.
  useEffect(() => {
    if (!editing && !pendingDelete) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setEditing(null)
        setEditForm(null)
        setPendingDelete(null)
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [editing, pendingDelete])

  const [form, setForm] = useState<FormState>({
    amount: '',
    currency: 'CNY',
    category: 'food',
    date: todayDate(timezone),
    note: '',
  })
  const [currencyTouched, setCurrencyTouched] = useState(false)

  // Default the currency to the household default once it loads (until
  // the user picks one explicitly).
  useEffect(() => {
    if (!householdLoading && household && !currencyTouched) {
      setForm((prev) => ({ ...prev, currency: defaultCurrency }))
    }
  }, [household, householdLoading, defaultCurrency, currencyTouched])

  const load = useCallback(() => {
    if (!household) return
    setLoading(true)
    setError(null)
    listTransactions(household.id, { limit: 50 })
      .then((list) => setRows(list))
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : '加载账本失败')
      })
      .finally(() => setLoading(false))
  }, [household])

  useEffect(() => {
    load()
  }, [load])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!household) return
    const amountError = validateAmountText(form.amount)
    if (amountError) {
      setFormError(amountError)
      return
    }
    if (!form.date) {
      setFormError('请选择日期')
      return
    }
    setFormError(null)
    setSubmitting(true)
    try {
      await createTransaction(buildCreatePayload(form, household.id, timezone))
      setForm({
        amount: '',
        currency: form.currency,
        category: 'food',
        date: todayDate(timezone),
        note: '',
      })
      load()
    } catch (err) {
      setFormError(err instanceof Error ? err.message : '记账失败')
    } finally {
      setSubmitting(false)
    }
  }

  const openEdit = (tx: Transaction) => {
    setEditing(tx)
    setEditError(null)
    setEditForm({
      amount: String(tx.amount),
      currency: tx.currency,
      category: tx.category,
      date: occurredAtToDate(tx.occurred_at, timezone),
      note: tx.note ?? '',
    })
  }

  const submitEdit = async (e: FormEvent) => {
    e.preventDefault()
    if (!editing || !editForm) return
    const amountError = validateAmountText(editForm.amount)
    if (amountError) {
      setEditError(amountError)
      return
    }
    if (!editForm.date) {
      setEditError('请选择日期')
      return
    }
    setEditError(null)
    try {
      await patchTransaction(editing.id, {
        amount: Number(normalizeAmountInput(editForm.amount)),
        category: editForm.category,
        note: editForm.note.trim() ? editForm.note.trim() : null,
        occurred_at: dateToOccurredAt(editForm.date, timezone),
      })
      setEditing(null)
      setEditForm(null)
      load()
    } catch (err) {
      setEditError(err instanceof Error ? err.message : '保存失败')
    }
  }

  const confirmDelete = async (tx: Transaction) => {
    setDeletingId(tx.id)
    try {
      await deleteTransaction(tx.id)
      setPendingDelete(null)
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除失败')
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <div className="page">
      <h1 className="page-title">记账</h1>
      {householdError && <p className="page-error">{householdError}</p>}
      <div className="transactions-layout">
        <section className="transactions-form-panel" aria-label="记一笔">
          <h2>记一笔</h2>
          <form onSubmit={(e) => void submit(e)}>
            <label className="form-field">
              金额
              <input
                type="text"
                inputMode="decimal"
                placeholder="例如 100.50"
                value={form.amount}
                onChange={(e) => setForm({ ...form, amount: e.target.value })}
                onBlur={() =>
                  setForm((prev) => ({ ...prev, amount: normalizeAmountInput(prev.amount) }))
                }
                aria-label="金额"
              />
            </label>
            <label className="form-field">
              货币
              <select
                value={form.currency}
                aria-label="货币"
                onChange={(e) => {
                  setCurrencyTouched(true)
                  setForm({ ...form, currency: e.target.value as Currency })
                }}
              >
                {SUPPORTED_CURRENCIES.map((c) => (
                  <option key={c} value={c}>
                    {c} {CURRENCY_LABELS[c]}
                  </option>
                ))}
              </select>
            </label>
            <label className="form-field">
              分类
              <select
                value={form.category}
                aria-label="分类"
                onChange={(e) => setForm({ ...form, category: e.target.value as TransactionCategory })}
              >
                {TRANSACTION_CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {CATEGORY_LABELS[c]}
                  </option>
                ))}
              </select>
            </label>
            <label className="form-field">
              日期
              <input
                type="date"
                value={form.date}
                aria-label="日期"
                onChange={(e) => setForm({ ...form, date: e.target.value })}
              />
            </label>
            <label className="form-field">
              备注
              <input
                type="text"
                placeholder="可选"
                value={form.note}
                onChange={(e) => setForm({ ...form, note: e.target.value })}
                aria-label="备注"
              />
            </label>
            {formError && (
              <p className="page-error" role="alert">
                {formError}
              </p>
            )}
            <button type="submit" className="btn btn-primary btn-lg" disabled={submitting || !household}>
              {submitting ? '保存中…' : '记一笔'}
            </button>
          </form>
        </section>

        <section className="transactions-list" aria-label="账本">
          {error && (
            <p className="page-error" role="alert">
              {error}
            </p>
          )}
          {loading && <p>加载中…</p>}
          {!loading && rows.length === 0 && !householdLoading && (
            <p className="page-empty">还没有记账</p>
          )}
          {rows.length > 0 && (
            <div className="tx-table-wrap">
              <table className="tx-table">
              <thead>
                <tr>
                  <th>日期</th>
                  <th>分类</th>
                  <th className="tx-amount">金额</th>
                  <th>备注</th>
                  <th>类型</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((tx) => {
                  const manual = isManualTransaction(tx)
                  return (
                    <tr key={tx.id}>
                      <td>{formatRelativeDate(tx.occurred_at, timezone)}</td>
                      <td>{CATEGORY_LABELS[tx.category]}</td>
                      <td className="tx-amount">
                        {formatAmount(tx.amount, resolveCurrency(tx.currency))}
                      </td>
                      <td className="tx-note">{tx.note?.trim() ? tx.note : '—'}</td>
                      <td>
                        {manual ? (
                          '手动'
                        ) : (
                          <span className="tx-receipt">
                            <StatusChip tone="accent" label="小票" />
                            <span className="tx-receipt-note">来自小票</span>
                          </span>
                        )}
                      </td>
                      <td>
                        {manual ? (
                          <span className="tx-actions">
                            <button
                              type="button"
                              className="btn btn-ghost btn-sm"
                              onClick={() => openEdit(tx)}
                            >
                              编辑
                            </button>
                            <button
                              type="button"
                              className="btn btn-ghost btn-sm tx-delete"
                              onClick={() => setPendingDelete(tx)}
                            >
                              删除
                            </button>
                          </span>
                        ) : (
                          <span className="tx-readonly">只读</span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
              </table>
            </div>
          )}
        </section>
      </div>

      {editing && editForm && (
        <div
          className="dialog-backdrop"
          role="presentation"
          onClick={(event) => {
            if (event.target === event.currentTarget) {
              setEditing(null)
              setEditForm(null)
            }
          }}
        >
          <div className="dialog" role="dialog" aria-modal="true" aria-label="编辑记账">
            <h2>编辑记账</h2>
            <form onSubmit={(e) => void submitEdit(e)}>
              <label className="form-field">
                金额（{editForm.currency}）
                <input
                  type="text"
                  inputMode="decimal"
                  value={editForm.amount}
                  onChange={(e) => setEditForm({ ...editForm, amount: e.target.value })}
                  aria-label="金额"
                />
              </label>
              <label className="form-field">
                分类
                <select
                  value={editForm.category}
                  aria-label="分类"
                  onChange={(e) =>
                    setEditForm({ ...editForm, category: e.target.value as TransactionCategory })
                  }
                >
                  {TRANSACTION_CATEGORIES.map((c) => (
                    <option key={c} value={c}>
                      {CATEGORY_LABELS[c]}
                    </option>
                  ))}
                </select>
              </label>
              <label className="form-field">
                日期
                <input
                  type="date"
                  value={editForm.date}
                  aria-label="日期"
                  onChange={(e) => setEditForm({ ...editForm, date: e.target.value })}
                />
              </label>
              <label className="form-field">
                备注
                <input
                  type="text"
                  value={editForm.note}
                  onChange={(e) => setEditForm({ ...editForm, note: e.target.value })}
                  aria-label="备注"
                />
              </label>
              {editError && (
                <p className="page-error" role="alert">
                  {editError}
                </p>
              )}
              <div className="dialog-actions">
                <button
                  type="button"
                  className="btn"
                  onClick={() => {
                    setEditing(null)
                    setEditForm(null)
                  }}
                >
                  取消
                </button>
                <button type="submit" className="btn btn-primary">
                  保存
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {pendingDelete && (
        <div
          className="dialog-backdrop"
          role="presentation"
          onClick={(event) => {
            if (event.target === event.currentTarget) {
              setPendingDelete(null)
            }
          }}
        >
          <div className="dialog" role="dialog" aria-modal="true" aria-label="确认删除">
            <h2>确认删除？</h2>
            <p>
              将删除这笔记账（
              {formatAmount(pendingDelete.amount, resolveCurrency(pendingDelete.currency))} ·{' '}
              {CATEGORY_LABELS[pendingDelete.category]}）。删除后无法恢复。
            </p>
            <div className="dialog-actions">
              <button type="button" className="btn" onClick={() => setPendingDelete(null)}>
                取消
              </button>
              <button
                type="button"
                className="btn btn-error"
                disabled={deletingId === pendingDelete.id}
                onClick={() => void confirmDelete(pendingDelete)}
              >
                确认删除
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
