/**
 * Upload receipt — design doc §8.4/§8.5 + §5.1.
 *
 * - Transport: `Taro.uploadFile` trên cả hai target (multipart `image` +
 *   `household_id`). Tiến độ từ `onProgressUpdate`.
 * - Idempotency-Key (F12): UUID v4 sinh một lần cho mỗi lần user pick, lưu
 *   trong page state gắn với file đã pick. Mọi retry của cùng pick — retry
 *   mạng, retry sau 401-refresh, user bấm 重新上传 — đều gửi cùng key.
 *   Pick mới sinh key mới.
 * - Validation client (§5.1, theo thứ tự, trước khi upload bắt đầu):
 *   type jpg/jpeg/png/webp → size ≤ 10 MB → ảnh đọc được. HEIC từ camera
 *   roll iOS: thử convert bằng `Taro.compressImage`, fail thì lỗi type.
 * - Response là 202 `{id, status: "pending"}` — upload thành công ≠ xử lý xong.
 */
import Taro from '@tarojs/taro'
import { apiUrl } from '../config/env'
import { ApiError, apiErrorToZh } from './errors'
import { ensureFreshAccessToken, getAccessToken } from './auth'
import { uuidv4 } from '../utils/uuid'

export const MAX_IMAGE_BYTES = 10 * 1024 * 1024

const ALLOWED_EXTENSIONS = new Set(['jpg', 'jpeg', 'png', 'webp'])

export type ImageValidationError = 'type' | 'size' | 'unreadable'

export const IMAGE_ERROR_ZH: Record<ImageValidationError, string> = {
  type: '仅支持 JPG、PNG、WebP 图片',
  size: '图片超过 10 MB，请重新拍摄或压缩后上传',
  unreadable: '图片无法读取，请重新拍摄',
}

export interface PickedImage {
  tempFilePath: string
  size: number
  name: string
}

function extensionOf(path: string): string {
  const base = path.split('/').pop() ?? ''
  const dot = base.lastIndexOf('.')
  return dot >= 0 ? base.slice(dot + 1).toLowerCase() : ''
}

/** Kiểm tra type/size từ thông tin file đã pick (chưa đọc bytes). */
export function validateImageFile(file: { size: number; path: string }): ImageValidationError | null {
  const ext = extensionOf(file.path)
  if (!ALLOWED_EXTENSIONS.has(ext)) return 'type'
  if (file.size > MAX_IMAGE_BYTES) return 'size'
  return null
}

/** Một UUID v4 mới cho mỗi lần user pick (không phải mỗi HTTP attempt). */
export function newIdempotencyKey(): string {
  return uuidv4()
}

export async function pickImage(source: 'camera' | 'album'): Promise<PickedImage> {
  const res = await Taro.chooseImage({
    count: 1,
    sizeType: ['compressed'],
    sourceType: [source],
  })
  const tempFilePath = res.tempFilePaths[0]
  const size = res.tempFiles?.[0]?.size ?? 0
  return { tempFilePath, size, name: tempFilePath.split('/').pop() ?? 'receipt.jpg' }
}

/**
 * Chuẩn bị ảnh đã pick: HEIC thì thử convert bằng compressImage (§5.1);
 * convert fail hoặc vẫn HEIC thì lỗi type. Trả về file dùng được để upload.
 */
export async function preparePickedImage(
  picked: PickedImage,
): Promise<{ ok: true; file: PickedImage } | { ok: false; error: ImageValidationError }> {
  const ext = extensionOf(picked.tempFilePath)
  if (ext === 'heic' || ext === 'heif') {
    try {
      const compressed = await Taro.compressImage({ src: picked.tempFilePath, quality: 80 })
      const converted: PickedImage = {
        tempFilePath: compressed.tempFilePath,
        size: picked.size,
        name: compressed.tempFilePath.split('/').pop() ?? 'receipt.jpg',
      }
      const err = validateImageFile({ size: converted.size, path: converted.tempFilePath })
      if (err) return { ok: false, error: err }
      return { ok: true, file: converted }
    } catch {
      return { ok: false, error: 'type' }
    }
  }
  const err = validateImageFile({ size: picked.size, path: picked.tempFilePath })
  if (err) return { ok: false, error: err }
  return { ok: true, file: picked }
}

export interface UploadReceiptInput {
  tempFilePath: string
  householdId: string
  /** Key của lần pick này — dùng lại qua mọi retry (§8.4). */
  idempotencyKey: string
  onProgress?: (percent: number) => void
}

export async function uploadReceipt(input: UploadReceiptInput): Promise<{ receiptId: string; status: string }> {
  // Refresh chủ động để upload dài không chết giữa chừng vì token hết hạn.
  await ensureFreshAccessToken()
  const token = getAccessToken()
  const task = Taro.uploadFile({
    url: apiUrl('/receipts'),
    filePath: input.tempFilePath,
    name: 'image',
    formData: { household_id: input.householdId },
    header: {
      Authorization: `Bearer ${token}`,
      'Idempotency-Key': input.idempotencyKey,
    },
    timeout: 60_000,
  }) as unknown as Promise<Taro.uploadFile.SuccessCallbackResult> & {
    onProgressUpdate?: (cb: (res: { progress: number }) => void) => void
  }
  task.onProgressUpdate?.((res) => input.onProgress?.(res.progress))
  let res: Taro.uploadFile.SuccessCallbackResult
  try {
    res = await task
  } catch {
    throw new ApiError(0, apiErrorToZh(0))
  }
  if (res.statusCode >= 200 && res.statusCode < 300) {
    const data = (typeof res.data === 'string' ? JSON.parse(res.data) : res.data) as {
      id?: string
      status?: string
    }
    if (!data.id) throw new ApiError(0, apiErrorToZh(0))
    return { receiptId: data.id, status: data.status ?? 'pending' }
  }
  throw new ApiError(res.statusCode, apiErrorToZh(res.statusCode))
}
