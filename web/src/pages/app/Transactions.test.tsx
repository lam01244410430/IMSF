import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { TransactionsPage } from './Transactions'
import { dateToOccurredAt, todayDate } from '../../lib/format'

const HOUSEHOLD = {
  id: '11111111-1111-1111-1111-111111111111',
  name: '我家',
  default_currency: 'CNY',
  timezone: 'Asia/Shanghai',
  locale: 'zh-CN',
  created_at: null,
  role: 'owner',
}

const MANUAL_ROW = {
  id: 'tx-manual',
  household_id: HOUSEHOLD.id,
  receipt_id: null,
  type: 'expense',
  amount: 100,
  currency: 'CNY',
  category: 'food',
  occurred_at: '2026-11-21T00:00:00+08:00',
  note: '买菜',
  created_at: null,
  updated_at: null,
}

const RECEIPT_ROW = {
  id: 'tx-receipt',
  household_id: HOUSEHOLD.id,
  receipt_id: '22222222-2222-2222-2222-222222222222',
  type: 'expense',
  amount: 250.5,
  currency: 'CNY',
  category: 'food',
  occurred_at: '2026-11-20T00:00:00+08:00',
  note: null,
  created_at: null,
  updated_at: null,
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('TransactionsPage', () => {
  let fetchMock: ReturnType<typeof vi.fn>
  let postBodies: unknown[]

  beforeEach(() => {
    postBodies = []
    fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (url.startsWith('/api/v2/households')) return Promise.resolve(jsonResponse([HOUSEHOLD]))
      if (url.startsWith('/api/v2/transactions') && init?.method === 'POST') {
        postBodies.push(JSON.parse(init.body as string))
        return Promise.resolve(jsonResponse({ ...MANUAL_ROW, id: 'tx-new' }, 201))
      }
      if (url.startsWith('/api/v2/transactions')) {
        return Promise.resolve(jsonResponse([MANUAL_ROW, RECEIPT_ROW]))
      }
      return Promise.resolve(jsonResponse(null, 404))
    })
    vi.stubGlobal('fetch', fetchMock)
    window.localStorage.clear()
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  function renderPage() {
    return render(
      <MemoryRouter>
        <TransactionsPage />
      </MemoryRouter>,
    )
  }

  it('manual rows are editable, receipt rows are read-only', async () => {
    renderPage()
    // Amounts render with formatAmount: trailing zeros stripped.
    expect(await screen.findByText('¥100')).toBeDefined()
    expect(screen.getByText('¥250.5')).toBeDefined()

    // Exactly one row offers 编辑 / 删除 — the manual one.
    expect(screen.getAllByRole('button', { name: '编辑' })).toHaveLength(1)
    expect(screen.getAllByRole('button', { name: '删除' })).toHaveLength(1)

    // The receipt row shows the 小票 chip + 来自小票 and 只读.
    expect(screen.getByText('来自小票')).toBeDefined()
    expect(screen.getByText('只读')).toBeDefined()

    const rows = screen.getAllByRole('row')
    const receiptRow = rows.find((r) => within(r).queryByText('来自小票'))
    expect(receiptRow).toBeDefined()
    expect(within(receiptRow as HTMLElement).queryByRole('button', { name: '编辑' })).toBeNull()
    expect(within(receiptRow as HTMLElement).queryByRole('button', { name: '删除' })).toBeNull()
  })

  it('the table sits in a horizontal-scroll wrapper (no page overflow on mobile)', async () => {
    const { container } = renderPage()
    await screen.findByText('¥100')
    const wrap = container.querySelector('.tx-table-wrap')
    expect(wrap).not.toBeNull()
    expect(wrap?.querySelector('table.tx-table')).not.toBeNull()
  })

  it('form validation rejects bad amounts before any POST', async () => {
    renderPage()
    await screen.findByText('¥100')

    fireEvent.change(screen.getByLabelText('金额'), { target: { value: '100.555' } })
    fireEvent.click(screen.getByRole('button', { name: '记一笔' }))
    expect(await screen.findByText('金额最多保留两位小数')).toBeDefined()
    expect(postBodies).toHaveLength(0)
  })

  it('submit posts type=expense with the household currency and a household-tz date', async () => {
    renderPage()
    await screen.findByText('¥100')

    fireEvent.change(screen.getByLabelText('金额'), { target: { value: '100.50' } })
    fireEvent.change(screen.getByLabelText('备注'), { target: { value: '午饭' } })
    fireEvent.click(screen.getByRole('button', { name: '记一笔' }))

    await waitFor(() => expect(postBodies).toHaveLength(1))
    expect(postBodies[0]).toEqual({
      household_id: HOUSEHOLD.id,
      type: 'expense',
      amount: 100.5,
      currency: 'CNY',
      category: 'food',
      occurred_at: dateToOccurredAt(todayDate('Asia/Shanghai'), 'Asia/Shanghai'),
      note: '午饭',
    })
  })
})
