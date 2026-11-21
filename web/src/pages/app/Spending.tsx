/**
 * Spending dashboard (/app/spending) — one currency at a time, never
 * summed across currencies. Currency selector (14, default = household
 * currency), month selector, monthly total card, by-category bars with
 * share %, and a tappable year-month list (tapping a month selects it).
 * The backend response always carries both groupings; the month list
 * comes from `by_month` of the selected year's summary.
 */
import { useCallback, useEffect, useState } from 'react'
import {
  CATEGORY_LABELS,
  getSpendingSummary,
  type SpendingSummary,
} from '../../lib/api'
import { useCurrentHousehold } from '../../lib/household'
import {
  CURRENCY_LABELS,
  currentMonth,
  formatAmount,
  monthLabel,
  monthRange,
  shiftMonth,
  SUPPORTED_CURRENCIES,
  yearRange,
  type Currency,
} from '../../lib/format'

export function SpendingPage() {
  const { household, defaultCurrency, timezone, loading: householdLoading, error: householdError } =
    useCurrentHousehold()
  const [currency, setCurrency] = useState<Currency>('CNY')
  const [currencyTouched, setCurrencyTouched] = useState(false)
  const [month, setMonth] = useState<string>(() => currentMonth(timezone))
  const [summary, setSummary] = useState<SpendingSummary | null>(null)
  const [yearMonths, setYearMonths] = useState<{ month: string; total: number }[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!householdLoading && household && !currencyTouched) {
      setCurrency(defaultCurrency)
    }
  }, [household, householdLoading, defaultCurrency, currencyTouched])

  const load = useCallback(() => {
    if (!household) return
    setLoading(true)
    setError(null)
    const { from, to } = monthRange(month, timezone)
    const year = Number(month.slice(0, 4))
    const yr = yearRange(year, timezone)
    Promise.all([
      getSpendingSummary(household.id, currency, { from, to }),
      getSpendingSummary(household.id, currency, { from: yr.from, to: yr.to }),
    ])
      .then(([monthSummary, yearSummary]) => {
        setSummary(monthSummary)
        setYearMonths([...yearSummary.by_month].sort((a, b) => b.month.localeCompare(a.month)))
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : '加载统计失败')
      })
      .finally(() => setLoading(false))
  }, [household, currency, month, timezone])

  useEffect(() => {
    load()
  }, [load])

  const total = summary?.total ?? 0
  const categories = [...(summary?.by_category ?? [])].sort((a, b) => b.total - a.total)

  return (
    <div className="page">
      <h1 className="page-title">消费统计</h1>
      {householdError && <p className="page-error">{householdError}</p>}
      <div className="spending-controls">
        <label className="form-field form-field-inline">
          货币
          <select
            value={currency}
            aria-label="货币"
            onChange={(e) => {
              setCurrencyTouched(true)
              setCurrency(e.target.value as Currency)
            }}
          >
            {SUPPORTED_CURRENCIES.map((c) => (
              <option key={c} value={c}>
                {c} {CURRENCY_LABELS[c]}
              </option>
            ))}
          </select>
        </label>
        <div className="month-picker" aria-label="选择月份">
          <button
            type="button"
            className="btn btn-sm"
            aria-label="上个月"
            onClick={() => setMonth((m) => shiftMonth(m, -1))}
          >
            ‹
          </button>
          <input
            type="month"
            value={month}
            aria-label="月份"
            onChange={(e) => {
              if (e.target.value) setMonth(e.target.value)
            }}
          />
          <button
            type="button"
            className="btn btn-sm"
            aria-label="下个月"
            onClick={() => setMonth((m) => shiftMonth(m, 1))}
          >
            ›
          </button>
        </div>
      </div>
      <p className="page-note">
        每种货币单独汇总，不混算、不换算。当前查看 {currency}（{CURRENCY_LABELS[currency]}）。
      </p>
      {error && (
        <p className="page-error" role="alert">
          {error}
        </p>
      )}
      {loading && <p>加载中…</p>}
      <div className="spending-dashboard">
        <section className="spending-total-card" aria-label="本月支出">
          <h2>{monthLabel(month)}支出</h2>
          <p className="spending-total">{formatAmount(total, currency)}</p>
          <p className="spending-total-currency">{currency}</p>
        </section>
        <section className="spending-categories" aria-label="分类汇总">
          <h2>分类汇总</h2>
          {categories.length === 0 && !loading && <p className="page-empty">本月暂无支出</p>}
          <ul className="category-bars">
            {categories.map((c) => {
              const pct = total > 0 ? Math.round((c.total / total) * 1000) / 10 : 0
              return (
                <li key={c.category} className="category-bar-row">
                  <span className="category-bar-label">{CATEGORY_LABELS[c.category]}</span>
                  <span
                    className="category-bar-track"
                    role="img"
                    aria-label={`${CATEGORY_LABELS[c.category]} ${formatAmount(c.total, currency)}，占 ${pct}%`}
                  >
                    <span className="category-bar-fill" style={{ width: `${pct}%` }} />
                  </span>
                  <span className="category-bar-value">
                    {formatAmount(c.total, currency)} · {pct}%
                  </span>
                </li>
              )
            })}
          </ul>
        </section>
      </div>
      <section className="spending-months" aria-label="按月查看">
        <h2>{month.slice(0, 4)} 年各月</h2>
        {yearMonths.length === 0 && !loading && <p className="page-empty">今年暂无支出</p>}
        <ul className="month-list">
          {yearMonths.map((m) => (
            <li key={m.month}>
              <button
                type="button"
                className={`month-item${m.month === month ? ' month-item-active' : ''}`}
                aria-current={m.month === month ? 'true' : undefined}
                onClick={() => setMonth(m.month)}
              >
                <span>{monthLabel(m.month)}</span>
                <span>{formatAmount(m.total, currency)}</span>
              </button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
