/**
 * useIsDesktop (weapp) — always false: a Mini Program has no desktop
 * viewport, so every desktop UI is dead code on weapp (design doc §12.1).
 */
export function useIsDesktop(): boolean {
  return false
}
