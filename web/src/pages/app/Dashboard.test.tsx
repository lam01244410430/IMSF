import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { DashboardPage } from './Dashboard'

const HOUSEHOLD = {
  id: '11111111-1111-1111-1111-111111111111',
  name: '我家',
  default_currency: 'CNY',
  timezone: 'Asia/Shanghai',
  locale: 'zh-CN',
  created_at: null,
  role: 'owner',
}

const FRIDGE = [
  {
    id: 'fridge-milk',
    household_id: HOUSEHOLD.id,
    receipt_id: null,
    receipt_line_id: null,
    raw_name: '牛奶',
    canonical_ingredient_id: null,
    quantity: 1,
    unit: '盒',
    price: 12,
    currency: 'CNY',
    storage_zone: 'fridge',
    added_date: '2026-11-20',
    auto_expiry_date: '2026-11-21',
    status: 'expired',
    consumed_at: null,
    created_at: null,
    updated_at: null,
    canonical_name: '牛奶',
    days_left: -1,
  },
  {
    id: 'fridge-eggs',
    household_id: HOUSEHOLD.id,
    receipt_id: null,
    receipt_line_id: null,
    raw_name: '鸡蛋',
    canonical_ingredient_id: null,
    quantity: 12,
    unit: '个',
    price: 18,
    currency: 'CNY',
    storage_zone: 'fridge',
    added_date: '2026-11-20',
    auto_expiry_date: '2026-11-23',
    status: 'expiring',
    consumed_at: null,
    created_at: null,
    updated_at: null,
    canonical_name: '鸡蛋',
    days_left: 1,
  },
  {
    id: 'fridge-rice',
    household_id: HOUSEHOLD.id,
    receipt_id: null,
    receipt_line_id: null,
    raw_name: '大米',
    canonical_ingredient_id: null,
    quantity: 5,
    unit: 'kg',
    price: 40,
    currency: 'CNY',
    storage_zone: 'pantry',
    added_date: '2026-11-20',
    auto_expiry_date: '2026-12-22',
    status: 'fresh',
    consumed_at: null,
    created_at: null,
    updated_at: null,
    canonical_name: '大米',
    days_left: 30,
  },
]

const TRANSACTIONS = [
  {
    id: 'tx-1',
    household_id: HOUSEHOLD.id,
    receipt_id: null,
    type: 'expense',
    amount: 50,
    currency: 'CNY',
    category: 'food',
    occurred_at: '2026-11-21T00:00:00+08:00',
    note: '午饭',
    created_at: null,
    updated_at: null,
  },
  {
    id: 'tx-2',
    household_id: HOUSEHOLD.id,
    receipt_id: null,
    type: 'income',
    amount: 1000,
    currency: 'CNY',
    category: 'other',
    occurred_at: '2026-11-20T00:00:00+08:00',
    note: '工资',
    created_at: null,
    updated_at: null,
  },
]

const EQUIPMENTS = [
  {
    id: 'eq-fridge',
    household_id: HOUSEHOLD.id,
    type: 'refrigerator',
    name: '冰箱',
    device_type: 'refrigerator',
    brand_model: null,
    usage_intensity: null,
    last_maintained_at: null,
    next_maintenance_date: '2026-11-20',
    rag_maintenance_notes: null,
    status: 'active',
    household_size: null,
    usage_per_week: null,
    maintenance_interval_days: 180,
    created_at: null,
    updated_at: null,
    days_until_maintenance: -2,
  },
  {
    id: 'eq-ac',
    household_id: HOUSEHOLD.id,
    type: 'air_conditioner',
    name: '空调',
    device_type: 'air_conditioner',
    brand_model: null,
    usage_intensity: null,
    last_maintained_at: null,
    next_maintenance_date: '2026-11-27',
    rag_maintenance_notes: null,
    status: 'active',
    household_size: null,
    usage_per_week: null,
    maintenance_interval_days: 90,
    created_at: null,
    updated_at: null,
    days_until_maintenance: 5,
  },
  {
    id: 'eq-washer',
    household_id: HOUSEHOLD.id,
    type: 'washing_machine',
    name: '洗衣机',
    device_type: 'washing_machine',
    brand_model: null,
    usage_intensity: null,
    last_maintained_at: null,
    next_maintenance_date: null,
    rag_maintenance_notes: null,
    status: 'active',
    household_size: null,
    usage_per_week: null,
    maintenance_interval_days: null,
    created_at: null,
    updated_at: null,
    days_until_maintenance: null,
  },
]

const NOTIFICATIONS = [
  {
    id: 'notif-1',
    user_id: 'user-1',
    household_id: HOUSEHOLD.id,
    type: 'lazy_tracking',
    ref_type: 'fridge_item',
    ref_id: 'fridge-eggs',
    channel: 'in_app',
    payload_json: { message: '鸡蛋快过期了，请确认是否已用完。' },
    status: 'sent',
    response: null,
    sent_at: '2026-11-22T08:00:00+08:00',
    responded_at: null,
    created_at: '2026-11-22T08:00:00+08:00',
  },
  {
    id: 'notif-2',
    user_id: 'user-1',
    household_id: HOUSEHOLD.id,
    type: 'expiry_reminder',
    ref_type: 'fridge_item',
    ref_id: 'fridge-milk',
    channel: 'in_app',
    payload_json: { message: '牛奶已过期。' },
    status: 'delivered',
    response: null,
    sent_at: '2026-11-21T08:00:00+08:00',
    responded_at: null,
    created_at: '2026-11-21T08:00:00+08:00',
  },
  {
    id: 'notif-3',
    user_id: 'user-1',
    household_id: HOUSEHOLD.id,
    type: 'lazy_tracking',
    ref_type: 'fridge_item',
    ref_id: 'fridge-rice',
    channel: 'in_app',
    payload_json: { message: '大米快过期了，请确认是否已用完。' },
    status: 'responded',
    response: 'used_up',
    sent_at: '2026-11-20T08:00:00+08:00',
    responded_at: '2026-11-20T09:00:00+08:00',
    created_at: '2026-11-20T08:00:00+08:00',
  },
]

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

interface FixtureOverrides {
  spending?: unknown
  fridge?: unknown
  transactions?: unknown
  equipments?: unknown
  notifications?: unknown
  spendingStatus?: number
}

function stubFetch(overrides: FixtureOverrides = {}) {
  const calls: string[] = []
  const spending =
    overrides.spending ??
    ({
      currency: 'CNY',
      total: 1234.5,
      by_category: [
        { category: 'food', total: 800 },
        { category: 'household', total: 300 },
        { category: 'maintenance', total: 134.5 },
      ],
      by_month: [{ month: '2026-11', total: 1234.5 }],
    } as const)
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string, init?: { method?: string }) => {
      calls.push(`${init?.method ?? 'GET'} ${url}`)
      if (url.startsWith('/api/v2/households')) return Promise.resolve(jsonResponse([HOUSEHOLD]))
      if (url.startsWith('/api/v2/spending/summary'))
        return Promise.resolve(jsonResponse(spending, overrides.spendingStatus ?? 200))
      if (url.startsWith('/api/v2/fridge/') && url.endsWith('/consume'))
        return Promise.resolve(jsonResponse({ ...FRIDGE[0], status: 'consumed' }))
      if (url.startsWith('/api/v2/fridge/') && url.endsWith('/extend'))
        return Promise.resolve(jsonResponse({ ...FRIDGE[1], days_left: 4 }))
      if (url.startsWith('/api/v2/fridge'))
        return Promise.resolve(jsonResponse(overrides.fridge ?? FRIDGE))
      if (url.startsWith('/api/v2/transactions'))
        return Promise.resolve(jsonResponse(overrides.transactions ?? TRANSACTIONS))
      if (url.startsWith('/api/v2/equipments'))
        return Promise.resolve(jsonResponse(overrides.equipments ?? EQUIPMENTS))
      if (url.startsWith('/api/v2/notifications'))
        return Promise.resolve(jsonResponse(overrides.notifications ?? NOTIFICATIONS))
      return Promise.resolve(jsonResponse(null, 404))
    }),
  )
  return calls
}

function renderPage() {
  return render(
    <MemoryRouter>
      <DashboardPage />
    </MemoryRouter>,
  )
}

describe('DashboardPage', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('renders all 7 widgets with real data', async () => {
    stubFetch()
    const { container } = renderPage()
    // Spending: total + top categories with % bars.
    await waitFor(() =>
      expect(container.querySelector('.dash-total')?.textContent).toBe('¥1,234.5'),
    )
    expect(screen.getByRole('region', { name: '本月支出' })).toBeDefined()
    // '餐饮' appears twice (spending bar + recent row) — check both exist.
    expect(screen.getAllByText('餐饮').length).toBeGreaterThanOrEqual(2)
    // Expiring: expired milk first, then eggs; 1-tap buttons present.
    expect(screen.getByRole('region', { name: '快过期' })).toBeDefined()
    expect(screen.getByText('牛奶')).toBeDefined()
    expect(screen.getByText('鸡蛋')).toBeDefined()
    expect(screen.queryByText('大米')).toBeNull()
    expect(screen.getByText('已过期 1 天')).toBeDefined()
    expect(screen.getByText('还剩 1 天')).toBeDefined()
    // Recent transactions (5–8 rows; here 2).
    expect(screen.getByRole('region', { name: '最近交易' })).toBeDefined()
    expect(screen.getByText('午饭')).toBeDefined()
    expect(screen.getByText('工资')).toBeDefined()
    // Quick actions link to the right places.
    expect(screen.getByRole('link', { name: '记一笔' }).getAttribute('href')).toBe(
      '/app/transactions',
    )
    expect(screen.getByRole('link', { name: '拍照' }).getAttribute('href')).toBe('/app/upload')
    expect(screen.getByRole('link', { name: '查菜谱' }).getAttribute('href')).toBe('/blog')
    expect(screen.getByRole('link', { name: '查保质期' }).getAttribute('href')).toBe(
      '/knowledge',
    )
    // Fridge counts: expired 1 / soon 1 / fresh 1.
    const fridge = screen.getByRole('region', { name: '冰箱' })
    expect(fridge.textContent).toContain('已过期')
    // Maintenance: overdue fridge first, then AC; undated washer skipped.
    const maint = screen.getByRole('region', { name: '保养提醒' })
    expect(maint.textContent).toContain('冰箱')
    expect(maint.textContent).toContain('保养已过期 2 天')
    expect(maint.textContent).toContain('空调')
    expect(maint.textContent).not.toContain('洗衣机')
    expect(maint.textContent?.indexOf('冰箱')).toBeLessThan(
      maint.textContent?.indexOf('空调') ?? 0,
    )
    // Notifications: 2 unread (open), latest 2 shown, responded one not counted.
    const notif = screen.getByRole('region', { name: '未读通知' })
    expect(notif.textContent).toContain('2')
    expect(screen.getByText('鸡蛋快过期了，请确认是否已用完。')).toBeDefined()
    expect(screen.getByText('牛奶已过期。')).toBeDefined()
    expect(screen.queryByText('大米快过期了，请确认是否已用完。')).toBeNull()
    // The widget is non-navigating: no link inside it, hint points at the bell.
    expect(notif.querySelector('a')).toBeNull()
    expect(screen.getByText('点右上角的铃铛查看全部通知')).toBeDefined()
  })

  it('shows honest empty states for a brand-new household', async () => {
    stubFetch({
      spending: { currency: 'CNY', total: 0, by_category: [], by_month: [] },
      fridge: [],
      transactions: [],
      equipments: [],
      notifications: [],
    })
    const { container } = renderPage()
    await waitFor(() =>
      expect(container.querySelector('.dash-total')?.textContent).toBe('¥0'),
    )
    expect(screen.getByText(/本月暂无支出/)).toBeDefined()
    expect(screen.getByText(/冰箱里没有快过期的食材/)).toBeDefined()
    expect(screen.getByText(/还没有交易/)).toBeDefined()
    expect(screen.getByText(/冰箱还是空的/)).toBeDefined()
    expect(screen.getByText(/暂无设备/)).toBeDefined()
    expect(screen.getByText(/暂无未读通知/)).toBeDefined()
    // First-action hints, no fabricated numbers. Each hint appears in
    // two widgets, so assert on all of them.
    for (const link of screen.getAllByRole('link', { name: '记第一笔' })) {
      expect(link.getAttribute('href')).toBe('/app/transactions')
    }
    for (const link of screen.getAllByRole('link', { name: '拍第一张小票' })) {
      expect(link.getAttribute('href')).toBe('/app/upload')
    }
  })

  it('1-tap 已用完 calls consume and refreshes the fridge', async () => {
    const calls = stubFetch()
    renderPage()
    await waitFor(() => expect(screen.getByText('牛奶')).toBeDefined())
    const buttons = screen.getAllByRole('button', { name: '已用完' })
    fireEvent.click(buttons[0])
    await waitFor(() =>
      expect(
        calls.some((c) => c === 'POST /api/v2/fridge/fridge-milk/consume'),
      ).toBe(true),
    )
    // Fridge list refetched after the action (widgets 2 and 5 share it).
    await waitFor(() =>
      expect(calls.filter((c) => c.startsWith('GET /api/v2/fridge?')).length).toBeGreaterThanOrEqual(
        2,
      ),
    )
  })

  it('1-tap 再放三天 calls extend with 3 days', async () => {
    const calls = stubFetch()
    renderPage()
    await waitFor(() => expect(screen.getByText('鸡蛋')).toBeDefined())
    const buttons = screen.getAllByRole('button', { name: '再放三天' })
    fireEvent.click(buttons[0])
    await waitFor(() =>
      expect(
        calls.some((c) => c === 'POST /api/v2/fridge/fridge-milk/extend'),
      ).toBe(true),
    )
  })

  it('shows a per-widget error when the spending summary fails', async () => {
    stubFetch({ spendingStatus: 500, spending: { detail: 'boom' } })
    renderPage()
    await waitFor(() =>
      expect(screen.getByText(/加载失败|boom/)).toBeDefined(),
    )
    // Other widgets still render their data.
    expect(screen.getByText('牛奶')).toBeDefined()
  })

  it('recent transactions show each row in its own currency', async () => {
    stubFetch({
      transactions: [
        ...TRANSACTIONS,
        {
          id: 'tx-usd',
          household_id: HOUSEHOLD.id,
          receipt_id: null,
          type: 'expense',
          amount: 12.34,
          currency: 'USD',
          category: 'food',
          occurred_at: '2026-11-19T00:00:00+08:00',
          note: '咖啡',
          created_at: null,
          updated_at: null,
        },
      ],
    })
    const { container } = renderPage()
    await waitFor(() => expect(screen.getByText('咖啡')).toBeDefined())
    // The USD row must show $ — not the household default ¥ (defect 1).
    const amounts = Array.from(
      container.querySelectorAll('.dash-tx-amount'),
    ).map((el) => el.textContent)
    expect(amounts).toContain('支出 $12.34')
    expect(amounts).not.toContain('支出 ¥12.34')
    // Same in the accessible name.
    expect(
      screen.getByRole('link', { name: '2026-11-19 餐饮 $12.34' }),
    ).toBeDefined()
  })

  it('notifications widget lists unread only, not merely open', async () => {
    // notif-1 is open but already seen — it must leave the list and
    // the count (defect 4).
    window.localStorage.setItem(
      'imsf2.notifications_seen',
      JSON.stringify(['notif-1']),
    )
    stubFetch()
    renderPage()
    const notif = await waitFor(() =>
      screen.getByRole('region', { name: '未读通知' }),
    )
    expect(notif.textContent).toContain('1')
    expect(screen.getByText('牛奶已过期。')).toBeDefined()
    expect(
      screen.queryByText('鸡蛋快过期了，请确认是否已用完。'),
    ).toBeNull()
  })

  it('refreshes the unread list when the bell marks notifications seen', async () => {
    stubFetch()
    renderPage()
    await waitFor(() =>
      expect(
        screen.getByText('鸡蛋快过期了，请确认是否已用完。'),
      ).toBeDefined(),
    )
    window.localStorage.setItem(
      'imsf2.notifications_seen',
      JSON.stringify(['notif-1', 'notif-2']),
    )
    window.dispatchEvent(new Event('imsf:notifications-seen'))
    await waitFor(() =>
      expect(screen.getByText(/暂无未读通知/)).toBeDefined(),
    )
  })

  it('fridge zero counts render neutral, not alarming', async () => {
    stubFetch({ fridge: [FRIDGE[2]] }) // only fresh rice: 0 expired, 0 soon
    const { container } = renderPage()
    await waitFor(() =>
      expect(container.querySelector('.dash-total')?.textContent).toBe(
        '¥1,234.5',
      ),
    )
    const fridge = screen.getByRole('region', { name: '冰箱' })
    const nums = fridge.querySelectorAll('.dash-count-num')
    expect(nums[0]?.textContent).toBe('0')
    expect(nums[0]?.className).not.toContain('dash-count-error')
    expect(nums[1]?.textContent).toBe('0')
    expect(nums[1]?.className).not.toContain('dash-count-warning')
  })

  it('spending summary is requested in the household default currency only', async () => {
    const calls = stubFetch()
    renderPage()
    await waitFor(() =>
      expect(screen.getAllByText('餐饮').length).toBeGreaterThanOrEqual(1),
    )
    const summaryCalls = calls.filter((c) => c.includes('/spending/summary'))
    expect(summaryCalls.length).toBeGreaterThanOrEqual(1)
    for (const c of summaryCalls) {
      const params = new URL(c.split(' ')[1], 'http://localhost').searchParams
      expect(params.get('currency')).toBe('CNY')
    }
  })
})
