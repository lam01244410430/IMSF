/**
 * UI store — Zustand client state (§8.7): toast queue (H5), tabBar selected
 * index, network.isOnline.
 */
import { create } from 'zustand'

export interface ToastItem {
  id: number
  message: string
  kind: 'success' | 'error' | 'info'
}

let toastSeq = 0

interface UiState {
  toasts: ToastItem[]
  tabBarSelected: number
  isOnline: boolean
  showToast: (message: string, kind?: ToastItem['kind']) => void
  dismissToast: (id: number) => void
  setTabBarSelected: (index: number) => void
  setOnline: (online: boolean) => void
}

export const useUiStore = create<UiState>()((set) => ({
  toasts: [],
  tabBarSelected: 0,
  isOnline: true,
  showToast: (message, kind = 'info') => {
    const id = ++toastSeq
    set((s) => ({ toasts: [...s.toasts, { id, message, kind }] }))
    // Toast tự ẩn sau 4s (lỗi: 6s — caller tự dismiss nếu cần giữ lâu hơn).
    setTimeout(() => {
      set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }))
    }, kind === 'error' ? 6000 : 4000)
  },
  dismissToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
  setTabBarSelected: (tabBarSelected) => set({ tabBarSelected }),
  setOnline: (isOnline) => set({ isOnline }),
}))
