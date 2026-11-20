/**
 * Store dùng chung cho confirmDialog imperative (DialogHost đọc store này).
 * Không import lib UI — an toàn cho cả 2 platform.
 */
import { create } from 'zustand'
import type { ConfirmDialogOptions } from './Dialog.types'

interface ConfirmDialogState {
  open: boolean
  title: string
  content: string
  confirmText: string
  cancelText: string
  resolve: ((value: boolean) => void) | null
  ask: (opts: ConfirmDialogOptions) => Promise<boolean>
  close: (result: boolean) => void
}

export const useConfirmDialogStore = create<ConfirmDialogState>()((set, get) => ({
  open: false,
  title: '',
  content: '',
  confirmText: '确认',
  cancelText: '取消',
  resolve: null,
  ask: (opts) =>
    new Promise<boolean>((resolve) => {
      set({
        open: true,
        title: opts.title,
        content: opts.content,
        confirmText: opts.confirmText ?? '确认',
        cancelText: opts.cancelText ?? '取消',
        resolve,
      })
    }),
  close: (result) => {
    const { resolve } = get()
    set({ open: false, resolve: null })
    resolve?.(result)
  },
}))
