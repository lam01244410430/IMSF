/**
 * Fridge (/app/fridge) — inventory grouped and sorted by expiry:
 * expired first, then expiring soon, then fresh. Expiry chips always
 * carry an icon AND text, never colour alone.
 *
 * Lazy Tracking 1-tap: 已用完 (POST /fridge/{id}/consume) and
 * 再放三天 (POST /fridge/{id}/extend {days: 3}). The same two actions
 * are also offered from the notifications bell, via the notifications
 * respond endpoint.
 */
import { useCallback, useEffect, useState } from 'react'
import {
  consumeFridgeItem,
  extendFridgeItem,
  listFridge,
  type FridgeItem,
} from '../../lib/api'
import { useCurrentHousehold } from '../../lib/household'
import { formatMoney, resolveCurrency } from '../../lib/format'
import { StatusChip, type ChipTone } from '../../components/StatusChip'

type ExpiryGroup = 'expired' | 'soon' | 'fresh' | 'none'

function expiryGroup(item: FridgeItem): ExpiryGroup {
  if (item.days_left === null) return 'none'
  if (item.days_left < 0) return 'expired'
  if (item.days_left <= 3) return 'soon'
  return 'fresh'
}

function expiryChip(item: FridgeItem): { tone: ChipTone; label: string } {
  const d = item.days_left
  if (d === null) return { tone: 'neutral', label: '无保质期' }
  if (d < 0) return { tone: 'error', label: `已过期 ${-d} 天` }
  if (d === 0) return { tone: 'warning', label: '今天过期' }
  if (d <= 3) return { tone: 'warning', label: `还剩 ${d} 天` }
  return { tone: 'success', label: `还剩 ${d} 天` }
}

const GROUP_ORDER: ExpiryGroup[] = ['expired', 'soon', 'fresh', 'none']
const GROUP_LABELS: Record<ExpiryGroup, string> = {
  expired: '已过期',
  soon: '快过期（3 天内）',
  fresh: '新鲜',
  none: '无保质期',
}

export function FridgePage() {
  const { household, loading: householdLoading, error: householdError } = useCurrentHousehold()
  const [items, setItems] = useState<FridgeItem[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [actingId, setActingId] = useState<string | null>(null)

  const load = useCallback(() => {
    if (!household) return
    setLoading(true)
    setError(null)
    listFridge(household.id, 100)
      .then((list) => {
        // Sort by expiry: nearest (or most overdue) first; no-expiry last.
        setItems(
          [...list].sort((a, b) => {
            const da = a.days_left ?? Number.POSITIVE_INFINITY
            const db = b.days_left ?? Number.POSITIVE_INFINITY
            return da - db
          }),
        )
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : '加载冰箱失败')
      })
      .finally(() => setLoading(false))
  }, [household])

  useEffect(() => {
    load()
  }, [load])

  const act = async (item: FridgeItem, action: 'consume' | 'extend') => {
    setActingId(item.id)
    setError(null)
    try {
      if (action === 'consume') await consumeFridgeItem(item.id)
      else await extendFridgeItem(item.id, 3)
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : '操作失败')
    } finally {
      setActingId(null)
    }
  }

  const grouped = new Map<ExpiryGroup, FridgeItem[]>()
  for (const item of items) {
    const g = expiryGroup(item)
    const arr = grouped.get(g) ?? []
    arr.push(item)
    grouped.set(g, arr)
  }

  return (
    <div className="page">
      <h1 className="page-title">冰箱</h1>
      {householdLoading && <p>加载中…</p>}
      {householdError && <p className="page-error">{householdError}</p>}
      {error && (
        <p className="page-error" role="alert">
          {error}
        </p>
      )}
      {!householdLoading && !householdError && !loading && items.length === 0 && (
        <p className="page-empty">冰箱还是空的——确认小票后，食材会出现在这里。</p>
      )}
      {loading && <p>加载中…</p>}
      {GROUP_ORDER.map((g) => {
        const list = grouped.get(g) ?? []
        if (list.length === 0) return null
        return (
          <section key={g} aria-label={GROUP_LABELS[g]}>
            <h2>
              {GROUP_LABELS[g]}（{list.length}）
            </h2>
            <ul className="fridge-list">
              {list.map((item) => {
                const chip = expiryChip(item)
                const name = item.canonical_name ?? item.raw_name
                return (
                  <li key={item.id} className="fridge-row">
                    <div className="fridge-info">
                      <span className="fridge-name">{name}</span>
                      <span className="fridge-meta">
                        {item.quantity} {item.unit}
                        {item.price !== null
                          ? ` · ${formatMoney(item.price, resolveCurrency(item.currency))}`
                          : ''}
                        {item.auto_expiry_date
                          ? ` · 到期 ${item.auto_expiry_date.slice(0, 10)}`
                          : ''}
                      </span>
                    </div>
                    <StatusChip tone={chip.tone} label={chip.label} />
                    <div className="fridge-actions">
                      <button
                        type="button"
                        className="btn btn-sm"
                        disabled={actingId === item.id}
                        onClick={() => void act(item, 'consume')}
                      >
                        已用完
                      </button>
                      <button
                        type="button"
                        className="btn btn-sm"
                        disabled={actingId === item.id}
                        onClick={() => void act(item, 'extend')}
                      >
                        再放三天
                      </button>
                    </div>
                  </li>
                )
              })}
            </ul>
          </section>
        )
      })}
    </div>
  )
}
