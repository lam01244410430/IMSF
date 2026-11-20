import { afterEach, describe, expect, it, vi } from 'vitest'
import { uuidv4 } from './uuid'

const V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/

describe('uuidv4', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('đúng định dạng v4 + duy nhất', () => {
    const ids = new Set(Array.from({ length: 100 }, () => uuidv4()))
    expect(ids.size).toBe(100)
    for (const id of ids) expect(id).toMatch(V4)
  })

  it('fallback khi không có crypto (runtime Mini Program cũ)', () => {
    vi.stubGlobal('crypto', undefined)
    const id = uuidv4()
    expect(id).toMatch(V4)
  })
})
