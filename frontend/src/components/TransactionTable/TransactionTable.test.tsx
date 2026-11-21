/**
 * Component test — TransactionTable (FE-04, design doc §12.4): đủ 6 cột,
 * dòng chi tay có 编辑/删除, dòng từ hoá đơn chỉ có chip 小票 (không nút),
 * số tiền formatAmount bỏ số 0 thừa.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import TransactionTable from './TransactionTable'
import type { Transaction } from '../../services/transactions'

const manualTx: Transaction = {
  id: 'tx-1',
  household_id: 'h-1',
  receipt_id: null,
  type: 'expense',
  amount: 100,
  currency: 'CNY',
  category: 'food',
  occurred_at: '2026-11-21T10:00:00+08:00',
  note: '午饭',
  created_at: '2026-11-21T10:00:00+08:00',
  updated_at: '2026-11-21T10:00:00+08:00',
}

const receiptTx: Transaction = {
  ...manualTx,
  id: 'tx-2',
  receipt_id: 'rc-1',
  amount: 132,
  note: '超市购物',
}

afterEach(() => {
  cleanup()
})

function renderTable(transactions: Transaction[] = [manualTx, receiptTx]) {
  const onEdit = vi.fn()
  const onDeleteRequest = vi.fn()
  render(
    <TransactionTable
      transactions={transactions}
      timezone='Asia/Shanghai'
      onEdit={onEdit}
      onDeleteRequest={onDeleteRequest}
    />,
  )
  return { onEdit, onDeleteRequest }
}

describe('TransactionTable', () => {
  it('render đủ 6 cột header: 日期 | 分类 | 金额 | 备注 | 类型 | 操作', () => {
    renderTable()
    for (const header of ['日期', '分类', '金额', '备注', '类型', '操作']) {
      expect(screen.getByText(header)).toBeTruthy()
    }
  })

  it('dòng chi tay có 编辑 + 删除; bấm 编辑 gọi onEdit với đúng tx', () => {
    const { onEdit } = renderTable()
    // Chỉ dòng chi tay có nút: 1 manual + 1 receipt → đúng 1 nút mỗi loại.
    expect(screen.getAllByText('编辑').length).toBe(1)
    expect(screen.getAllByText('删除').length).toBe(1)
    fireEvent.click(screen.getByText('编辑'))
    expect(onEdit).toHaveBeenCalledTimes(1)
    expect(onEdit).toHaveBeenCalledWith(manualTx)
  })

  it('bấm 删除 gọi onDeleteRequest với đúng tx', () => {
    const { onDeleteRequest } = renderTable()
    fireEvent.click(screen.getByText('删除'))
    expect(onDeleteRequest).toHaveBeenCalledTimes(1)
    expect(onDeleteRequest).toHaveBeenCalledWith(manualTx)
  })

  it('dòng từ hoá đơn hiện chip 小票 + 来自小票, KHÔNG có nút sửa/xoá', () => {
    renderTable()
    expect(screen.getByText('小票')).toBeTruthy()
    expect(screen.getByText('来自小票')).toBeTruthy()
    expect(screen.getByText('手动')).toBeTruthy()
    // Đã assert ở test trên: chỉ 1 nút 编辑 + 1 nút 删除 cho cả bảng
    // (thuộc về dòng chi tay) — dòng hoá đơn không có nút nào.
    expect(screen.getAllByText('编辑').length).toBe(1)
    expect(screen.getAllByText('删除').length).toBe(1)
  })

  it('số tiền formatAmount bỏ số 0 thừa: 100 → ¥100 (không phải ¥100.00)', () => {
    renderTable([manualTx])
    expect(screen.getByText('¥100')).toBeTruthy()
    expect(screen.queryByText('¥100.00')).toBeNull()
  })

  it('ghi chú trống hiện —', () => {
    renderTable([{ ...manualTx, note: '   ' }])
    expect(screen.getByText('—')).toBeTruthy()
  })
})
