/**
 * useIsDesktop (H5) — FE-04 desktop breakpoint (design doc §12.1).
 *
 * Single threshold: min-width 1024px (= tokens.breakpoints.md). The initial
 * value is read from matchMedia at once so the first render already knows
 * (no layout flash), and a `change` listener updates it live on resize.
 *
 * No CSS @media: inline styles can't be overridden by a stylesheet without
 * !important, and Mini Program WXSS doesn't support @media at all.
 */
import { useEffect, useState } from 'react'

const QUERY = '(min-width: 1024px)'

export function useIsDesktop(): boolean {
  const [isDesktop, setIsDesktop] = useState<boolean>(() => window.matchMedia(QUERY).matches)

  useEffect(() => {
    const mq = window.matchMedia(QUERY)
    const onChange = (event: MediaQueryListEvent): void => {
      setIsDesktop(event.matches)
    }
    mq.addEventListener('change', onChange)
    // Re-read in case the viewport crossed the threshold between render and effect.
    setIsDesktop(mq.matches)
    return () => {
      mq.removeEventListener('change', onChange)
    }
  }, [])

  return isDesktop
}
