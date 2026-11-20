/**
 * Dialog — props dùng chung cho cả 2 platform (design doc §8.2).
 * Ngoài component khai báo, primitive này xuất thêm `confirmDialog(opts)`
 * imperative (Promise<boolean>) + `DialogHost` (mount 1 lần ở app shell,
 * Step 4) — store dùng chung, không import lib UI nào.
 */
import type { ReactNode } from 'react'

export interface DialogProps {
  open: boolean
  title: string
  content: ReactNode
  confirmText?: string
  cancelText?: string
  onConfirm: () => void
  onCancel: () => void
}

export interface ConfirmDialogOptions {
  title: string
  content: string
  confirmText?: string
  cancelText?: string
}

export default DialogProps
