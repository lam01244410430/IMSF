/**
 * Current-household hook for the app pages. Fetches GET /households once
 * per page mount and picks the stored household id
 * (`imsf2.household_id`, set at login) when it belongs to the user,
 * otherwise the first household. Returns the household's
 * `default_currency` (for form/summary defaults) and `timezone` (for
 * date defaults and month ranges).
 */
import { useEffect, useState } from 'react'
import { getStoredHouseholdId } from './auth'
import { listHouseholds, type Household } from './api'
import { resolveCurrency, type Currency } from './format'

export interface CurrentHousehold {
  household: Household | null
  loading: boolean
  error: string | null
  /** Default currency of the household, resolved to one of the 14 (else CNY). */
  defaultCurrency: Currency
  /** Household timezone (else Asia/Shanghai). */
  timezone: string
}

export function useCurrentHousehold(): CurrentHousehold {
  const [household, setHousehold] = useState<Household | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    listHouseholds()
      .then((list) => {
        if (cancelled) return
        const stored = getStoredHouseholdId()
        const current = list.find((h) => h.id === stored) ?? list[0] ?? null
        setHousehold(current)
        setLoading(false)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : '加载家庭信息失败')
        setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  return {
    household,
    loading,
    error,
    defaultCurrency: resolveCurrency(household?.default_currency),
    timezone: household?.timezone || 'Asia/Shanghai',
  }
}
