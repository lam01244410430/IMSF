/**
 * useIsDesktop hook test (FE-04, design doc §12.1/§12.8): matches true/false
 * + live update when the `change` listener fires (resize across 1024px).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { useIsDesktop } from './useIsDesktop'

type Listener = (event: { matches: boolean }) => void

/**
 * Controllable window.matchMedia: every MediaQueryList it creates captures
 * its `change` listeners, so the test can fire resize events on all of them
 * (the hook calls matchMedia once at render and once in its effect).
 */
function mockMatchMedia(initialMatches: boolean) {
  const created: { listeners: Set<Listener> }[] = []
  const createMql = () => {
    const entry = { listeners: new Set<Listener>() }
    created.push(entry)
    return {
      matches: initialMatches,
      media: '(min-width: 1024px)',
      onchange: null,
      addListener: (cb: Listener) => {
        entry.listeners.add(cb)
      },
      removeListener: (cb: Listener) => {
        entry.listeners.delete(cb)
      },
      addEventListener: (_type: string, cb: Listener) => {
        entry.listeners.add(cb)
      },
      removeEventListener: (_type: string, cb: Listener) => {
        entry.listeners.delete(cb)
      },
      dispatchEvent: () => false,
    }
  }
  window.matchMedia = vi.fn(createMql) as unknown as typeof window.matchMedia
  return {
    fire(matches: boolean) {
      for (const entry of created) {
        for (const cb of entry.listeners) cb({ matches })
      }
    },
  }
}

const originalMatchMedia = window.matchMedia

beforeEach(() => {
  vi.clearAllMocks()
})

afterEach(() => {
  window.matchMedia = originalMatchMedia
})

describe('useIsDesktop', () => {
  it('returns false when matchMedia matches:false', () => {
    mockMatchMedia(false)
    const { result } = renderHook(() => useIsDesktop())
    expect(result.current).toBe(false)
  })

  it('returns true when matchMedia matches:true', () => {
    mockMatchMedia(true)
    const { result } = renderHook(() => useIsDesktop())
    expect(result.current).toBe(true)
  })

  it('updates when the change listener fires', () => {
    const media = mockMatchMedia(false)
    const { result } = renderHook(() => useIsDesktop())
    expect(result.current).toBe(false)
    act(() => {
      media.fire(true)
    })
    expect(result.current).toBe(true)
    act(() => {
      media.fire(false)
    })
    expect(result.current).toBe(false)
  })
})
