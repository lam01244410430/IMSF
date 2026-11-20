/**
 * Unit tests — upload.ts: validation (§5.1), idempotency key giữ qua retry (§8.4).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { taroMock, __resetTaroStorage } from '../test/taroMock'
import {
  IMAGE_ERROR_ZH,
  newIdempotencyKey,
  preparePickedImage,
  uploadReceipt,
  validateImageFile,
} from './upload'
import { STORAGE_KEYS } from './auth'

beforeEach(() => {
  __resetTaroStorage()
  vi.clearAllMocks()
  taroMock.setStorageSync(STORAGE_KEYS.access, 'access-valid')
})

describe('validateImageFile', () => {
  it('chấp nhận jpg/png/webp ≤ 10MB', () => {
    expect(validateImageFile({ size: 1024, path: '/tmp/a.jpg' })).toBeNull()
    expect(validateImageFile({ size: 10 * 1024 * 1024, path: '/tmp/a.PNG' })).toBeNull()
    expect(validateImageFile({ size: 100, path: '/tmp/a.webp' })).toBeNull()
  })
  it('từ chối type khác + size > 10MB', () => {
    expect(validateImageFile({ size: 100, path: '/tmp/a.heic' })).toBe('type')
    expect(validateImageFile({ size: 100, path: '/tmp/a.pdf' })).toBe('type')
    expect(validateImageFile({ size: 10 * 1024 * 1024 + 1, path: '/tmp/a.jpg' })).toBe('size')
    expect(IMAGE_ERROR_ZH.type).toContain('JPG')
    expect(IMAGE_ERROR_ZH.size).toContain('10 MB')
  })
})

describe('preparePickedImage — HEIC', () => {
  it('HEIC convert được qua compressImage thì dùng file mới', async () => {
    taroMock.compressImage.mockResolvedValue({ tempFilePath: '/tmp/converted.jpg' })
    const res = await preparePickedImage({ tempFilePath: '/tmp/a.heic', size: 1000, name: 'a.heic' })
    expect(res.ok).toBe(true)
    if (res.ok) expect(res.file.tempFilePath).toBe('/tmp/converted.jpg')
  })
  it('HEIC convert fail thì lỗi type', async () => {
    taroMock.compressImage.mockRejectedValue(new Error('no'))
    const res = await preparePickedImage({ tempFilePath: '/tmp/a.heic', size: 1000, name: 'a.heic' })
    expect(res).toEqual({ ok: false, error: 'type' })
  })
})

describe('uploadReceipt — idempotency', () => {
  it('retry cùng pick gửi cùng Idempotency-Key; pick mới sinh key mới', async () => {
    taroMock.uploadFile
      .mockRejectedValueOnce(new Error('network'))
      .mockResolvedValue({ statusCode: 202, data: JSON.stringify({ id: 'r-1', status: 'pending' }) })
    const key = newIdempotencyKey()
    const input = { tempFilePath: '/tmp/a.jpg', householdId: 'h-1', idempotencyKey: key }
    await expect(uploadReceipt(input)).rejects.toMatchObject({ status: 0 })
    const res = await uploadReceipt(input)
    expect(res).toEqual({ receiptId: 'r-1', status: 'pending' })
    const headers = taroMock.uploadFile.mock.calls.map(
      (c) => (c[0] as { header: Record<string, string> }).header['Idempotency-Key'],
    )
    expect(headers).toEqual([key, key])
    expect(newIdempotencyKey()).not.toBe(key)
  })

  it('gửi multipart đúng field + header Authorization', async () => {
    taroMock.uploadFile.mockResolvedValue({
      statusCode: 202,
      data: JSON.stringify({ id: 'r-2', status: 'pending' }),
    })
    await uploadReceipt({ tempFilePath: '/tmp/a.jpg', householdId: 'h-9', idempotencyKey: 'k-1' })
    expect(taroMock.uploadFile).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'image',
        filePath: '/tmp/a.jpg',
        formData: { household_id: 'h-9' },
        header: expect.objectContaining({
          Authorization: 'Bearer access-valid',
          'Idempotency-Key': 'k-1',
        }),
      }),
    )
  })

  it('400 từ server → ApiError 400 (không retry)', async () => {
    taroMock.uploadFile.mockResolvedValue({ statusCode: 400, data: '{}' })
    await expect(
      uploadReceipt({ tempFilePath: '/tmp/a.jpg', householdId: 'h-1', idempotencyKey: 'k' }),
    ).rejects.toMatchObject({ status: 400 })
    expect(taroMock.uploadFile).toHaveBeenCalledTimes(1)
  })
})
