/**
 * 消费统计 — FE-03 (design doc §6 hàng 4): tổng chi tiêu theo tháng +
 * theo danh mục, từ GET /spending/summary.
 *
 * - Một tiền tệ tại một thời điểm (API bắt buộc currency, thiếu → 400):
 *   selector CNY/VND, mặc định = default_currency của nhà (không thì CNY).
 *   KHÔNG BAO GIỜ cộng CNY + VND.
 * - Tháng chọn: tháng hiện tại mặc định, nút trước/sau; nút sau disable khi
 *   đã ở tháng hiện tại. Tổng tháng gọi summary với from = đầu tháng,
 *   to = đầu tháng sau (theo timezone của nhà).
 * - Danh sách các tháng trong năm (by_month của summary cả năm): bấm một
 *   tháng để xem tháng đó.
 * - Chỉ tính type='expense' (backend) — thu nhập không vào đây.
 */
import { useEffect, useMemo, useState } from 'react'
import { Text, View } from '@tarojs/components'
import { useQuery } from '@tanstack/react-query'
import PageHeader from '../../components/PageHeader/PageHeader'
import OfflineBanner from '../../components/OfflineBanner/OfflineBanner'
import Button from '../../ui/primitives/Button'
import Icon from '../../ui/primitives/Icon'
import ListRow from '../../ui/primitives/ListRow'
import Skeleton from '../../ui/primitives/Skeleton'
import { tokens } from '../../ui/tokens'
import { CATEGORY_LABELS, getSpendingSummary } from '../../services/transactions'
import { goBack, goLogin } from '../../config/routes'
import { useSessionStore } from '../../store/session'
import { listHouseholds } from '../../services/households'
import type { Currency } from '../../utils/format'
import {
  currentMonth,
  formatAmount,
  monthLabel,
  monthRange,
  round2,
  shiftMonth,
  yearRange,
} from '../../utils/format'

const CURRENCIES: { key: Currency; label: string }[] = [
  { key: 'CNY', label: '人民币 ¥' },
  { key: 'VND', label: '越南盾 ₫' },
]

export default function Spending() {
  const householdId = useSessionStore((s) => s.currentHouseholdId)
  const isLoggedIn = useSessionStore((s) => s.isLoggedIn)
  // default_currency/timezone lấy từ GET /households (đầy đủ field) — session
  // store chỉ giữ HouseholdSummary {id, name} (xem services/auth.ts).
  const householdsQuery = useQuery({
    queryKey: ['households'],
    queryFn: () => listHouseholds(),
    enabled: isLoggedIn,
  })
  const currentHousehold = householdsQuery.data?.find((h) => h.id === householdId)
  const defaultCurrency: Currency = currentHousehold?.default_currency === 'VND' ? 'VND' : 'CNY'
  const timezone = currentHousehold?.timezone ?? 'Asia/Shanghai'

  const thisMonth = useMemo(() => currentMonth(timezone), [timezone])
  const [currency, setCurrency] = useState<Currency>('CNY')
  const [currencyTouched, setCurrencyTouched] = useState(false)
  // defaultCurrency đến từ GET /households (load async) — đồng bộ lại khi
  // query về, trừ khi user đã tự chọn tiền tệ.
  useEffect(() => {
    if (!currencyTouched && householdsQuery.data) setCurrency(defaultCurrency)
  }, [householdsQuery.data, defaultCurrency, currencyTouched])
  const [month, setMonth] = useState(thisMonth)
  const year = Number(month.slice(0, 4))

  const monthBounds = useMemo(() => monthRange(month, timezone), [month, timezone])
  const yearBounds = useMemo(() => yearRange(year, timezone), [year, timezone])

  const monthQuery = useQuery({
    queryKey: ['spending-summary', householdId, currency, month],
    queryFn: () =>
      getSpendingSummary(householdId as string, currency, { from: monthBounds.from, to: monthBounds.to }),
    enabled: Boolean(householdId),
  })
  const yearQuery = useQuery({
    queryKey: ['spending-summary', householdId, currency, year],
    queryFn: () =>
      getSpendingSummary(householdId as string, currency, { from: yearBounds.from, to: yearBounds.to }),
    enabled: Boolean(householdId),
  })

  // Skeleton chỉ hiện khi load lần đầu >300ms (§7.2).
  const [showSkeleton, setShowSkeleton] = useState(false)
  useEffect(() => {
    if (!monthQuery.isLoading) {
      setShowSkeleton(false)
      return
    }
    const t = setTimeout(() => setShowSkeleton(true), 300)
    return () => clearTimeout(t)
  }, [monthQuery.isLoading])

  const summary = monthQuery.data
  const total = summary?.total ?? 0
  const byCategory = [...(summary?.by_category ?? [])].sort((a, b) => b.total - a.total)
  const maxCategory = byCategory[0]?.total ?? 0
  const byMonth = [...(yearQuery.data?.by_month ?? [])]
    .filter((m) => m.month <= thisMonth)
    .sort((a, b) => b.month.localeCompare(a.month))

  return (
    <View>
      <PageHeader title='消费统计' subtitle='每月支出汇总' showBack onBack={() => void goBack()} />
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
            <View style={{ display: 'flex', flexDirection: 'row', gap: 8 }}>
              {CURRENCIES.map((c) => (
                <Button
                  key={c.key}
                  variant={currency === c.key ? 'primary' : 'outline'}
                  onClick={() => {
                    setCurrency(c.key)
                    setCurrencyTouched(true)
                  }}
                >
                  {c.label}
                </Button>
              ))}
            </View>
            <View
              style={{
                display: 'flex',
                flexDirection: 'row',
                alignItems: 'center',
                justifyContent: 'space-between',
                backgroundColor: tokens.color.surface,
                borderRadius: 16,
                paddingLeft: 8,
                paddingRight: 8,
                paddingTop: 4,
                paddingBottom: 4,
              }}
            >
              <Button variant='ghost' ariaLabel='上个月' onClick={() => setMonth(shiftMonth(month, -1))}>
                <Icon name='chevron-left' size={20} color={tokens.color.onSurface} />
              </Button>
              <Text style={{ fontSize: 16, fontWeight: 600, color: tokens.color.onSurface }}>
                {monthLabel(month)}
              </Text>
              <Button
                variant='ghost'
                ariaLabel='下个月'
                disabled={month >= thisMonth}
                onClick={() => setMonth(shiftMonth(month, 1))}
              >
                <Icon name='chevron-right' size={20} color={tokens.color.onSurface} />
              </Button>
            </View>
            {monthQuery.isLoading && showSkeleton ? (
              <Skeleton rows={4} />
            ) : monthQuery.isError ? (
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
                <Button variant='outline' onClick={() => void monthQuery.refetch()}>
                  重试
                </Button>
              </View>
            ) : (
              <>
                <View
                  style={{
                    backgroundColor: tokens.color.surface,
                    borderRadius: 16,
                    padding: 16,
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 4,
                  }}
                >
                  <Text style={{ fontSize: 14, color: tokens.color.onSurfaceVariant }}>本月支出</Text>
                  <Text style={{ fontSize: 28, fontWeight: 700, color: tokens.color.onSurface }}>
                    {formatAmount(total, currency)}
                  </Text>
                  {total === 0 ? (
                    <Text style={{ fontSize: 14, color: tokens.color.onSurfaceVariant }}>本月还没有支出</Text>
                  ) : null}
                </View>
                <View style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  <Text style={{ fontSize: 16, fontWeight: 600, color: tokens.color.onSurface }}>分类汇总</Text>
                  {byCategory.length === 0 ? (
                    <Text style={{ fontSize: 14, color: tokens.color.onSurfaceVariant }}>
                      本月暂无分类支出
                    </Text>
                  ) : (
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
                      {byCategory.map((c) => {
                        const share = total > 0 ? round2((c.total / total) * 100) : 0
                        const widthPct = maxCategory > 0 ? Math.max(4, round2((c.total / maxCategory) * 100)) : 0
                        return (
                          <View key={c.category} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                            <View
                              style={{
                                display: 'flex',
                                flexDirection: 'row',
                                justifyContent: 'space-between',
                              }}
                            >
                              <Text style={{ fontSize: 14, color: tokens.color.onSurface }}>
                                {CATEGORY_LABELS[c.category]}
                              </Text>
                              <Text style={{ fontSize: 14, color: tokens.color.onSurface }}>
                                {formatAmount(c.total, currency)} · {share}%
                              </Text>
                            </View>
                            <View
                              style={{
                                height: 8,
                                borderRadius: 4,
                                backgroundColor: tokens.color.surfaceVariant,
                              }}
                            >
                              <View
                                style={{
                                  height: 8,
                                  width: `${widthPct}%`,
                                  borderRadius: 4,
                                  backgroundColor: tokens.color.accent,
                                }}
                              />
                            </View>
                          </View>
                        )
                      })}
                    </View>
                  )}
                </View>
                <View style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  <Text style={{ fontSize: 16, fontWeight: 600, color: tokens.color.onSurface }}>
                    {year}年各月
                  </Text>
                  {byMonth.length === 0 ? (
                    <Text style={{ fontSize: 14, color: tokens.color.onSurfaceVariant }}>今年暂无支出记录</Text>
                  ) : (
                    <View style={{ backgroundColor: tokens.color.surface, borderRadius: 16 }}>
                      {byMonth.map((m) => (
                        <ListRow
                          key={m.month}
                          title={monthLabel(m.month)}
                          subtitle={m.month === month ? '当前查看' : undefined}
                          amount={formatAmount(m.total, currency)}
                          onClick={() => setMonth(m.month)}
                        />
                      ))}
                    </View>
                  )}
                </View>
              </>
            )}
          </>
        )}
      </View>
    </View>
  )
}
