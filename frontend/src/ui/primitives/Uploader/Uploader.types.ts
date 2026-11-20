/**
 * Uploader — SHELL hiển thị thuần (design doc §8.2 "Uploader shell").
 * Transport thuộc về services/upload.ts (§8.5): page gọi pickImage rồi
 * truyền files vào đây để hiển thị. Primitive này KHÔNG dùng NutUI
 * Uploader (transport tích hợp của nó xung đột với quyền sở hữu đó —
 * NutUI Uploader đã được kiểm chứng build ở Gate 0).
 */
export interface UploaderFileItem {
  name: string
  src?: string
  status: 'ready' | 'uploading' | 'success' | 'error'
}

export interface UploaderProps {
  files: UploaderFileItem[]
  onAdd: () => void
  onRemove: (index: number) => void
  disabled?: boolean
  /** 0–100 khi đang upload; undefined = không upload. */
  progress?: number
}

export default UploaderProps
