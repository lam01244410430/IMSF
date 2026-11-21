/**
 * Maintenance (/app/maintenance) — not in the sidebar; linked from
 * 我的. Equipment list (GET /equipments) + maintenance history per
 * equipment + add-maintenance form (POST /equipments/{id}/maintenance).
 * When a cost is logged the backend creates a ledger transaction and
 * returns it — the history shows that link. cost=0 logs cost 0 with NO
 * ledger row (transactions.amount has CHECK > 0), which the form
 * states plainly.
 */
import { useCallback, useEffect, useState, type FormEvent } from 'react'
import {
  getMaintenanceHistory,
  listEquipments,
  logMaintenance,
  MAINTENANCE_TYPE_LABELS,
  type Equipment,
  type MaintenanceLog,
  type MaintenanceType,
} from '../../lib/api'
import { useCurrentHousehold } from '../../lib/household'
import {
  CURRENCY_LABELS,
  dateToOccurredAt,
  formatAmount,
  resolveCurrency,
  SUPPORTED_CURRENCIES,
  todayDate,
  type Currency,
} from '../../lib/format'

const MAINTENANCE_TYPES: MaintenanceType[] = ['cleaning', 'filter_replace', 'repair', 'inspection']

export function MaintenancePage() {
  const { household, defaultCurrency, timezone, loading: householdLoading, error: householdError } =
    useCurrentHousehold()
  const [equipments, setEquipments] = useState<Equipment[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [history, setHistory] = useState<MaintenanceLog[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [formOk, setFormOk] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [form, setForm] = useState({
    performed_at: todayDate(timezone),
    maintenance_type: 'cleaning' as MaintenanceType,
    note: '',
    cost: '',
    currency: 'CNY' as Currency,
  })

  const load = useCallback(() => {
    if (!household) return
    setLoading(true)
    setError(null)
    listEquipments(household.id)
      .then((list) => {
        setEquipments(list)
        if (list.length > 0 && !selectedId) setSelectedId(list[0].id)
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : '加载设备失败')
      })
      .finally(() => setLoading(false))
  }, [household, selectedId])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    if (!household) setForm((prev) => ({ ...prev, currency: defaultCurrency }))
  }, [household, defaultCurrency])

  useEffect(() => {
    if (!selectedId) {
      setHistory([])
      return
    }
    let cancelled = false
    setHistoryLoading(true)
    getMaintenanceHistory(selectedId)
      .then((list) => {
        if (!cancelled) setHistory(list)
      })
      .catch(() => {
        if (!cancelled) setHistory([])
      })
      .finally(() => {
        if (!cancelled) setHistoryLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [selectedId])

  const selected = equipments.find((e) => e.id === selectedId) ?? null

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!selected) return
    setFormError(null)
    setFormOk(null)
    const costText = form.cost.trim()
    let cost: number | null = null
    if (costText !== '') {
      if (!/^\d+(\.\d{1,2})?$/.test(costText)) {
        setFormError('费用请输入正确的金额（最多两位小数）')
        return
      }
      cost = Number(costText)
      if (cost < 0) {
        setFormError('费用不能为负数')
        return
      }
    }
    if (!form.performed_at) {
      setFormError('请选择保养日期')
      return
    }
    setSubmitting(true)
    try {
      const res = await logMaintenance(selected.id, {
        performed_at: dateToOccurredAt(form.performed_at, timezone),
        maintenance_type: form.maintenance_type,
        note: form.note.trim() ? form.note.trim() : null,
        cost,
        currency: cost !== null ? form.currency : null,
      })
      setFormOk(
        res.transaction
          ? `已记录，并记账 ${formatAmount(res.transaction.amount, resolveCurrency(res.transaction.currency))}。`
          : cost === 0
            ? '已记录费用 0（按后端规则，费用为 0 时不产生账本记录）。'
            : '已记录。',
      )
      setForm((prev) => ({ ...prev, note: '', cost: '' }))
      load()
    } catch (err) {
      setFormError(err instanceof Error ? err.message : '记录失败')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="page">
      <h1 className="page-title">设备保养</h1>
      {householdError && <p className="page-error">{householdError}</p>}
      {error && (
        <p className="page-error" role="alert">
          {error}
        </p>
      )}
      {householdLoading && <p>加载中…</p>}
      {loading && <p>加载中…</p>}
      {!loading && equipments.length === 0 && !householdLoading && (
        <p className="page-empty">暂无设备</p>
      )}
      <div className="maintenance-layout">
        <section className="maintenance-list" aria-label="设备列表">
          <h2>设备</h2>
          <ul className="equipment-list">
            {equipments.map((eq) => (
              <li key={eq.id}>
                <button
                  type="button"
                  className={`equipment-item${eq.id === selectedId ? ' equipment-item-active' : ''}`}
                  aria-current={eq.id === selectedId ? 'true' : undefined}
                  onClick={() => setSelectedId(eq.id)}
                >
                  <span className="equipment-name">{eq.name ?? eq.type}</span>
                  <span className="equipment-meta">
                    {eq.type}
                    {eq.next_maintenance_date
                      ? eq.days_until_maintenance !== null && eq.days_until_maintenance < 0
                        ? ` · 保养已过期 ${-eq.days_until_maintenance} 天`
                        : ` · 下次保养 ${eq.next_maintenance_date.slice(0, 10)}`
                      : ' · 未设置保养周期'}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>

        {selected && (
          <section className="maintenance-detail" aria-label="保养记录">
            <h2>{selected.name ?? selected.type} — 保养记录</h2>
            <p className="page-note">
              上次保养：
              {selected.last_maintained_at ? selected.last_maintained_at.slice(0, 10) : '暂无记录'}
              {selected.maintenance_interval_days
                ? ` · 周期 ${selected.maintenance_interval_days} 天`
                : ''}
            </p>
            {historyLoading && <p>加载中…</p>}
            {history.length === 0 && !historyLoading && <p className="page-empty">暂无保养记录</p>}
            <ul className="maintenance-history">
              {history.map((log) => (
                <li key={log.id} className="maintenance-log">
                  <span>
                    {log.performed_at ? log.performed_at.slice(0, 10) : '—'} ·{' '}
                    {MAINTENANCE_TYPE_LABELS[log.maintenance_type]}
                  </span>
                  <span>
                    {log.cost !== null
                      ? formatAmount(log.cost, resolveCurrency(log.currency))
                      : '无费用'}
                    {log.transaction_id ? ' · 已记账' : ''}
                  </span>
                  {log.note ? <span className="maintenance-log-note">{log.note}</span> : null}
                </li>
              ))}
            </ul>

            <h3>新增保养记录</h3>
            <form onSubmit={(e) => void submit(e)} className="maintenance-form">
              <label className="form-field">
                保养日期
                <input
                  type="date"
                  value={form.performed_at}
                  aria-label="保养日期"
                  onChange={(e) => setForm({ ...form, performed_at: e.target.value })}
                />
              </label>
              <label className="form-field">
                保养类型
                <select
                  value={form.maintenance_type}
                  aria-label="保养类型"
                  onChange={(e) =>
                    setForm({ ...form, maintenance_type: e.target.value as MaintenanceType })
                  }
                >
                  {MAINTENANCE_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {MAINTENANCE_TYPE_LABELS[t]}
                    </option>
                  ))}
                </select>
              </label>
              <label className="form-field">
                费用（可选，留空表示无费用）
                <input
                  type="text"
                  inputMode="decimal"
                  placeholder="0 表示费用为 0（不产生账本记录）"
                  value={form.cost}
                  onChange={(e) => setForm({ ...form, cost: e.target.value })}
                  aria-label="费用"
                />
              </label>
              <label className="form-field">
                费用货币
                <select
                  value={form.currency}
                  aria-label="费用货币"
                  onChange={(e) => setForm({ ...form, currency: e.target.value as Currency })}
                >
                  {SUPPORTED_CURRENCIES.map((c) => (
                    <option key={c} value={c}>
                      {c} {CURRENCY_LABELS[c]}
                    </option>
                  ))}
                </select>
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
              {formOk && (
                <p className="page-ok" role="status">
                  {formOk}
                </p>
              )}
              <button type="submit" className="btn btn-primary" disabled={submitting}>
                {submitting ? '保存中…' : '记录保养'}
              </button>
            </form>
          </section>
        )}
      </div>
    </div>
  )
}
