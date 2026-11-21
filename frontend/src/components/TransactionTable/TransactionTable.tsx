/**
 * TransactionTable — bảng giao dịch desktop thật (FE-04, design doc §12.4).
 *
 * Shared component, KHÔNG có platform file: nó chỉ render khi
 * `useIsDesktop()` true (H5 ≥1024px), mà hook luôn false trên weapp nên
 * phía weapp đây là dead code không bao giờ render. Chỉ dùng Taro
 * primitives (View/Text) + tokens — KHÔNG MUI (MUI cấm ngoài primitives,
 * §8.2, và sẽ vỡ build weapp).
 *
 * Bảng thật theo nghĩa layout: cột thẳng hàng qua
 * `display: 'table' / 'table-row' / 'table-cell'` (Taro không có <table>).
 * Header: 日期 | 分类 | 金额 | 备注 | 类型 | 操作. Dòng chi tay: text
 * button 编辑 (accent) + 删除 (error); dòng từ hoá đơn: chip 小票 +
 * 来自小票, KHÔNG nút (chỉ đọc — PATCH/DELETE sẽ 409). Số tiền dùng
 * formatAmount (bỏ số 0 thừa, quy tắc FE-03) + chữ tabular.
 *
 * LỆCH KHỎI BRIEF (ghi rõ, không lặng lẽ):
 * - Hover dòng (`tokens.action.hover`): KHÔNG làm được bằng inline style
 *   (không biểu diễn được `:hover`), Taro `ViewProps` không có prop
 *   `onMouseEnter`/`onMouseLeave` (typecheck sẽ fail), và một rule
 *   `:hover` trong file `.scss` chung sẽ lọt vào build weapp (WXSS không
 *   hỗ trợ `:hover` — cùng lý do §12.1 cấm `@media`). Không có pattern
 *   hover nào cho Taro primitive trong codebase (chỉ MUI theme `&:hover`).
 *   Màu hover dự kiến vẫn là `tokens.action.hover` khi nào có cơ chế.
 * - Cột 类型 không dùng `TYPE_LABELS`: theo §12.4 nội dung cột là chip
 *   小票 + 来自小票 (dòng hoá đơn) hoặc text 手动 (dòng chi tay) — không
 *   còn chỗ cho 支出/收入; import thừa sẽ fail lint.
 */
import { Text, View } from '@tarojs/components'
import { tokens } from '../../ui/tokens'
import {
  CATEGORY_LABELS,
  isManualTransaction,
  type Transaction,
} from '../../services/transactions'
import { formatAmount, formatRelativeDate } from '../../utils/format'

export interface TransactionTableProps {
  transactions: Transaction[]
  timezone: string
  onEdit: (tx: Transaction) => void
  /**
   * Yêu cầu xoá một dòng chi tay. Page implement bằng cách mở dialog sửa
   * hiện có (`openEdit(tx)`) — dialog đó đã có nút 删除 chạy đúng flow
   * confirm + deleteMutation của page. Chọn cách này vì chạm ít code nhất:
   * không thêm state, không thêm mutation, không đổi flow xoá; user bấm
   * 删除 ở bảng → dialog sửa mở → bấm 删除这笔记账 trong dialog để xác nhận.
   */
  onDeleteRequest: (tx: Transaction) => void
}

/** Bề rộng cột (table-layout fixed, tổng 100%). */
const COLUMN_WIDTHS = ['15%', '12%', '16%', '27%', '14%', '16%'] as const

function ReceiptChip() {
  return (
    <View
      style={{
        backgroundColor: tokens.color.accentContainer,
        borderRadius: 8,
        paddingTop: 2,
        paddingBottom: 2,
        paddingLeft: 8,
        paddingRight: 8,
      }}
    >
      <Text style={{ fontSize: 12, fontWeight: 500, color: tokens.color.onAccentContainer }}>小票</Text>
    </View>
  )
}

export default function TransactionTable({ transactions, timezone, onEdit, onDeleteRequest }: TransactionTableProps) {
  return (
    <View
      style={{
        backgroundColor: tokens.color.surface,
        borderRadius: tokens.shape.card,
        paddingLeft: 16,
        paddingRight: 16,
      }}
    >
      <View style={{ display: 'table', width: '100%', tableLayout: 'fixed' }}>
        <View style={{ display: 'table-row' }}>
          {['日期', '分类', '金额', '备注', '类型', '操作'].map((label, i) => (
            <Text
              key={label}
              style={{
                display: 'table-cell',
                width: COLUMN_WIDTHS[i],
                fontSize: 14,
                fontWeight: 600,
                color: tokens.color.onSurfaceVariant,
                textAlign: i === 2 ? 'right' : 'left',
                paddingTop: 12,
                paddingBottom: 12,
                borderBottomWidth: 1,
                borderBottomStyle: 'solid',
                borderBottomColor: tokens.color.divider,
              }}
            >
              {label}
            </Text>
          ))}
        </View>
        {transactions.map((tx, rowIndex) => {
          const manual = isManualTransaction(tx)
          const isLast = rowIndex === transactions.length - 1
          return (
            <View key={tx.id} style={{ display: 'table-row' }}>
              <Text
                style={{
                  display: 'table-cell',
                  fontSize: 14,
                  color: tokens.color.onSurface,
                  paddingTop: 12,
                  paddingBottom: 12,
                  borderBottomWidth: isLast ? 0 : 1,
                  borderBottomStyle: 'solid',
                  borderBottomColor: tokens.color.divider,
                }}
              >
                {formatRelativeDate(tx.occurred_at, timezone)}
              </Text>
              <Text
                style={{
                  display: 'table-cell',
                  fontSize: 14,
                  color: tokens.color.onSurface,
                  paddingTop: 12,
                  paddingBottom: 12,
                  borderBottomWidth: isLast ? 0 : 1,
                  borderBottomStyle: 'solid',
                  borderBottomColor: tokens.color.divider,
                }}
              >
                {CATEGORY_LABELS[tx.category]}
              </Text>
              <Text
                style={{
                  display: 'table-cell',
                  fontSize: 14,
                  color: tokens.color.onSurface,
                  textAlign: 'right',
                  fontFeatureSettings: '"tnum"',
                  paddingTop: 12,
                  paddingBottom: 12,
                  borderBottomWidth: isLast ? 0 : 1,
                  borderBottomStyle: 'solid',
                  borderBottomColor: tokens.color.divider,
                }}
              >
                {formatAmount(tx.amount, tx.currency)}
              </Text>
              <View
                style={{
                  display: 'table-cell',
                  paddingTop: 12,
                  paddingBottom: 12,
                  borderBottomWidth: isLast ? 0 : 1,
                  borderBottomStyle: 'solid',
                  borderBottomColor: tokens.color.divider,
                }}
              >
                <View style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  <Text style={{ fontSize: 14, color: tokens.color.onSurface }}>
                    {tx.note?.trim() ? tx.note : '—'}
                  </Text>
                </View>
              </View>
              <View
                style={{
                  display: 'table-cell',
                  paddingTop: 12,
                  paddingBottom: 12,
                  borderBottomWidth: isLast ? 0 : 1,
                  borderBottomStyle: 'solid',
                  borderBottomColor: tokens.color.divider,
                }}
              >
                {manual ? (
                  <Text style={{ fontSize: 14, color: tokens.color.onSurface }}>手动</Text>
                ) : (
                  <View style={{ display: 'flex', flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                    <ReceiptChip />
                    <Text style={{ fontSize: 13, color: tokens.color.onSurfaceVariant }}>来自小票</Text>
                  </View>
                )}
              </View>
              <View
                style={{
                  display: 'table-cell',
                  paddingTop: 12,
                  paddingBottom: 12,
                  borderBottomWidth: isLast ? 0 : 1,
                  borderBottomStyle: 'solid',
                  borderBottomColor: tokens.color.divider,
                }}
              >
                {manual ? (
                  <View style={{ display: 'flex', flexDirection: 'row', alignItems: 'center', gap: 16 }}>
                    <Text
                      style={{ fontSize: 14, fontWeight: 500, color: tokens.color.accent }}
                      onClick={() => onEdit(tx)}
                    >
                      编辑
                    </Text>
                    <Text
                      style={{ fontSize: 14, fontWeight: 500, color: tokens.color.error }}
                      onClick={() => onDeleteRequest(tx)}
                    >
                      删除
                    </Text>
                  </View>
                ) : null}
              </View>
            </View>
          )
        })}
      </View>
    </View>
  )
}
