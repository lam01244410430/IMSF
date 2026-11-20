/**
 * Unit tests — http.ts: auth header, 401 → refresh single-flight, retry
 * policy, error mapping (§8.4, §8.6).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { taroMock, __resetTaroStorage } from '../test/taroMock'
import { request } from './http'
import { ApiError } from './errors'
import { STORAGE_KEYS, setSessionExpiredHandler } from './auth'

function mockOk(data: unknown, statusCode = 200) {
  return { statusCode, data, header: {} }
}

beforeEach(() => {
  __resetTaroStorage()
  vi.clearAllMocks()
  setSessionExpiredHandler(null)
  taroMock.setStorageSync(STORAGE_KEYS.access, 'access-old')
  taroMock.setStorageSync(STORAGE_KEYS.refresh, 'refresh-valid')
})

describe('request — auth header', () => {
  it('gắn Authorization: Bearer <access> khi auth mặc định', async () => {
    taroMock.request.mockResolvedValue(mockOk({ ok: true }))
    await request('/receipts/1')
    expect(taroMock.request).toHaveBeenCalledWith(
      expect.objectContaining({
        url: expect.stringContaining('/api/v2/receipts/1'),
        header: expect.objectContaining({ Authorization: 'Bearer access-old' }),
      }),
    )
  })

  it('không gắn Authorization khi auth: false', async () => {
    taroMock.request.mockResolvedValue(mockOk({ ok: true }))
    await request('/auth/wechat', { method: 'POST', body: { code: 'x' }, auth: false })
    const header = (taroMock.request.mock.calls[0][0] as { header: Record<string, string> }).header
    expect(header.Authorization).toBeUndefined()
  })
})

describe('request — 401 + refresh single-flight', () => {
  it('5 request đồng thời gặp 401 chỉ refresh 1 lần, cả 5 retry 1 lần với token mới', async () => {
    let receiptCalls = 0
    let refreshCalls = 0
    taroMock.request.mockImplementation((opts: { url: string }) => {
      if (opts.url.includes('/auth/refresh')) {
        refreshCalls += 1
        return Promise.resolve(mockOk({ access_token: 'access-new' }))
      }
      receiptCalls += 1
      if (receiptCalls <= 5) return Promise.resolve(mockOk({ detail: 'expired' }, 401))
      return Promise.resolve(mockOk({ id: 'r1' }))
    })
    const results = await Promise.all([
      request('/receipts/1'),
      request('/receipts/2'),
      request('/receipts/3'),
      request('/receipts/4'),
      request('/receipts/5'),
    ])
    expect(refreshCalls).toBe(1)
    expect(results).toHaveLength(5)
    // Các lần retry dùng token mới.
    const retryCalls = taroMock.request.mock.calls.filter((c) => {
      const o = c[0] as { header: Record<string, string> }
      return o.header.Authorization === 'Bearer access-new'
    })
    expect(retryCalls.length).toBe(5)
    expect(taroMock.getStorageSync(STORAGE_KEYS.access)).toBe('access-new')
  })

  it('refresh fail → xóa cả hai token + gọi session-expired handler đúng 1 lần', async () => {
    const handler = vi.fn()
    setSessionExpiredHandler(handler)
    taroMock.request.mockImplementation((opts: { url: string }) => {
      if (opts.url.includes('/auth/refresh')) return Promise.resolve(mockOk({ detail: 'bad' }, 401))
      return Promise.resolve(mockOk({ detail: 'expired' }, 401))
    })
    await expect(request('/receipts/1')).rejects.toBeInstanceOf(ApiError)
    expect(taroMock.getStorageSync(STORAGE_KEYS.access)).toBe('')
    expect(taroMock.getStorageSync(STORAGE_KEYS.refresh)).toBe('')
    expect(handler).toHaveBeenCalledTimes(1)
  })
})

describe('request — retry policy', () => {
  it('GET retry tối đa 2 lần khi lỗi mạng rồi thành công', async () => {
    taroMock.request
      .mockRejectedValueOnce(new Error('network'))
      .mockRejectedValueOnce(new Error('network'))
      .mockResolvedValue(mockOk({ ok: true }))
    const res = await request<{ ok: boolean }>('/receipts')
    expect(res.ok).toBe(true)
    expect(taroMock.request).toHaveBeenCalledTimes(3)
  })

  it('POST không auto-retry khi lỗi mạng', async () => {
    taroMock.request.mockRejectedValue(new Error('network'))
    await expect(request('/receipts/1/confirm', { method: 'POST', body: {} })).rejects.toMatchObject({
      status: 0,
    })
    expect(taroMock.request).toHaveBeenCalledTimes(1)
  })

  it('không retry 4xx', async () => {
    taroMock.request.mockResolvedValue(mockOk({ detail: 'bad' }, 400))
    await expect(request('/receipts')).rejects.toMatchObject({ status: 400 })
    expect(taroMock.request).toHaveBeenCalledTimes(1)
  })

  it('GET retry khi 503 rồi thành công', async () => {
    taroMock.request.mockResolvedValueOnce(mockOk({}, 503)).mockResolvedValue(mockOk({ ok: true }))
    const res = await request<{ ok: boolean }>('/receipts')
    expect(res.ok).toBe(true)
    expect(taroMock.request).toHaveBeenCalledTimes(2)
  })
})

describe('request — error mapping (§8.6)', () => {
  it.each([
    [400, '图片格式或大小不符合要求'],
    [403, '您没有权限查看该家庭的内容'],
    [404, '该内容已不存在'],
    [409, '这张小票已处理过'],
    [422, '请检查数量、单位和价格后重试'],
    [500, '服务器开小差了'],
  ])('status %i → zh-CN message', async (status, fragment) => {
    taroMock.request.mockResolvedValue(mockOk({}, status))
    let err: unknown
    try {
      await request('/receipts')
    } catch (e) {
      err = e
    }
    expect(err).toBeInstanceOf(ApiError)
    if (err instanceof ApiError) {
      expect(err.status).toBe(status)
      expect(err.messageZh).toContain(fragment)
    }
  })
})
