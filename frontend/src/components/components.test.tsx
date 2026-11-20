/**
 * Component tests (Step 4): StatusChip, PageHeader, ReceiptRow, EmptyState,
 * ReceiptList — business components dùng View/Text Taro + primitives.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import StatusChip from './StatusChip/StatusChip'
import PageHeader from './PageHeader/PageHeader'
import ReceiptRow from './ReceiptRow/ReceiptRow'
import EmptyState from './EmptyState/EmptyState'
import ReceiptList from './ReceiptList/ReceiptList'
import type { Receipt } from '../services/receipts'

afterEach(() => {
  cleanup()
})

const receipt = (over: Partial<Receipt>): Receipt => ({
  id: 'r-1',
  household_id: 'hh-1',
  uploaded_by_user_id: 'u-1',
  image_url: 'https://x/1.jpg',
  store_name: '沃尔玛',
  purchased_at: new Date().toISOString(),
  total_amount: 123.45,
  currency: 'CNY',
  status: 'completed',
  ocr_raw_text: null,
  error_message: null,
  processed_at: null,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  ...over,
})

describe('StatusChip', () => {
  it('renders the right label for every status', () => {
    const cases = [
      ['completed', '已完成'],
      ['pending', '处理中'],
      ['processing', '处理中'],
      ['needs_review', '需核对'],
      ['failed', '识别失败'],
    ] as const
    for (const [status, label] of cases) {
      render(<StatusChip status={status} />)
      expect(screen.getByText(label)).toBeTruthy()
      cleanup()
    }
  })
})

describe('PageHeader', () => {
  it('renders title + subtitle and fires back', () => {
    const onBack = vi.fn()
    render(<PageHeader title='IMSF-v2' subtitle='拍小票，自动记账入库' showBack onBack={onBack} />)
    expect(screen.getByText('IMSF-v2')).toBeTruthy()
    expect(screen.getByText('拍小票，自动记账入库')).toBeTruthy()
    fireEvent.click(screen.getByLabelText('返回'))
    expect(onBack).toHaveBeenCalledTimes(1)
  })
})

describe('ReceiptRow', () => {
  it('shows store, relative date, amount and chip for a completed receipt', () => {
    render(<ReceiptRow receipt={receipt({})} onClick={() => {}} />)
    expect(screen.getByText('沃尔玛')).toBeTruthy()
    expect(screen.getByText('今天', { exact: false })).toBeTruthy()
    expect(screen.getByText('¥123.45')).toBeTruthy()
    expect(screen.getByText('已完成')).toBeTruthy()
  })

  it('shows — instead of an amount while processing', () => {
    render(<ReceiptRow receipt={receipt({ status: 'processing', total_amount: 0 })} onClick={() => {}} />)
    expect(screen.getByText('—')).toBeTruthy()
    expect(screen.getByText('处理中')).toBeTruthy()
  })

  it('falls back to 未知商家 when the store name is missing', () => {
    render(<ReceiptRow receipt={receipt({ store_name: null })} onClick={() => {}} />)
    expect(screen.getByText('未知商家')).toBeTruthy()
  })
})

describe('EmptyState', () => {
  it('renders title/body/action and fires onAction', () => {
    const onAction = vi.fn()
    render(
      <EmptyState
        icon='camera'
        title='还没有小票'
        body='拍下第一张小票，自动记账并同步到冰箱。'
        actionLabel='立即拍照'
        onAction={onAction}
      />,
    )
    expect(screen.getByText('还没有小票')).toBeTruthy()
    fireEvent.click(screen.getByText('立即拍照'))
    expect(onAction).toHaveBeenCalledTimes(1)
  })

  it('renders without an action button when no action is given', () => {
    render(<EmptyState icon='camera' title='冰箱即将上线' body='第一批食材入库后，这里会显示保质期提醒。' />)
    expect(screen.getByText('冰箱即将上线')).toBeTruthy()
    expect(screen.queryByRole('button')).toBeNull()
  })
})

describe('ReceiptList', () => {
  const rows = [
    receipt({ id: 'r-1', store_name: '沃尔玛' }),
    receipt({ id: 'r-2', store_name: '永辉超市', status: 'needs_review', total_amount: 56.0 }),
    receipt({ id: 'r-3', store_name: '盒马', status: 'processing', total_amount: 0 }),
  ]
  const base = {
    isLoading: false,
    showSkeleton: false,
    isError: false,
    onRetry: () => {},
    onSelect: () => {},
  }

  it('renders rows and respects the limit', () => {
    render(<ReceiptList receipts={rows} limit={2} {...base} />)
    expect(screen.getByText('沃尔玛')).toBeTruthy()
    expect(screen.getByText('永辉超市')).toBeTruthy()
    expect(screen.queryByText('盒马')).toBeNull()
  })

  it('shows the error panel with a retry button', () => {
    const onRetry = vi.fn()
    render(<ReceiptList receipts={[]} isError onRetry={onRetry} isLoading={false} showSkeleton={false} onSelect={() => {}} />)
    expect(screen.getByText('加载失败，请检查网络后重试')).toBeTruthy()
    fireEvent.click(screen.getByText('重试'))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('shows the empty state when there are no receipts', () => {
    render(
      <ReceiptList
        receipts={[]}
        {...base}
        emptyState={<div>还没有小票</div>}
      />,
    )
    expect(screen.getByText('还没有小票')).toBeTruthy()
  })
})
