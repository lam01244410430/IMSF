/**
 * Upload draft store — Zustand client state (§8.7).
 * Giữ temp path + idempotency key của lần pick hiện tại để button retry gửi
 * lại cùng file với cùng key (không pick lại). Queue offline đầy đủ là GĐ3.
 */
import { create } from 'zustand'
import { newIdempotencyKey } from '../services/upload'
import type { PickedImage } from '../services/upload'

export type UploadDraftStatus = 'idle' | 'picked' | 'uploading' | 'done' | 'error'

interface UploadDraftState {
  file: PickedImage | null
  /** Key của lần pick này — sinh một lần khi pick, dùng lại qua retry. */
  idempotencyKey: string | null
  progress: number
  error: string | null
  status: UploadDraftStatus
  /** User pick ảnh mới → key mới (§8.4). */
  setPicked: (file: PickedImage) => void
  setProgress: (percent: number) => void
  setUploading: () => void
  setDone: () => void
  setError: (message: string) => void
  clear: () => void
}

export const useUploadDraftStore = create<UploadDraftState>()((set) => ({
  file: null,
  idempotencyKey: null,
  progress: 0,
  error: null,
  status: 'idle',
  setPicked: (file) =>
    set({ file, idempotencyKey: newIdempotencyKey(), progress: 0, error: null, status: 'picked' }),
  setProgress: (progress) => set({ progress }),
  setUploading: () => set({ status: 'uploading', error: null }),
  setDone: () => set({ status: 'done', progress: 100 }),
  setError: (error) => set({ error, status: 'error' }),
  clear: () => set({ file: null, idempotencyKey: null, progress: 0, error: null, status: 'idle' }),
}))
