/**
 * Regression test — muiTheme must build without throwing.
 *
 * 2026-11-21: the H5 app crashed at startup with "Minified MUI error #6"
 * because typography lineHeight was passed as px strings ("36px") while
 * `responsiveFontSizes` (mandated by design doc §3.3) requires unitless
 * line heights. Importing muiTheme runs responsiveFontSizes at module load,
 * so this test fails if the crash returns.
 */
import { describe, expect, it } from 'vitest'
import { muiTheme } from './muiTheme'
import { tokens } from './tokens'

describe('muiTheme', () => {
  it('builds without throwing (responsiveFontSizes)', () => {
    expect(muiTheme).toBeDefined()
    expect(muiTheme.typography).toBeDefined()
  })

  it('keeps line heights as unitless ratios of the token px values', () => {
    const t = tokens.typography
    // h1: 28px / 36px -> 36/28; body1: 16px / 24px -> 1.5; button: 14px / 20px
    expect(typeof muiTheme.typography.h1.lineHeight).toBe('number')
    expect(muiTheme.typography.h1.lineHeight).toBeCloseTo(t.h1.lineHeight / t.h1.size, 4)
    expect(muiTheme.typography.body1.lineHeight).toBeCloseTo(t.body1.lineHeight / t.body1.size, 4)
    expect(muiTheme.typography.button.lineHeight).toBeCloseTo(
      t.button.lineHeight / t.button.size,
      4,
    )
    expect(muiTheme.typography.caption.lineHeight).toBeCloseTo(
      t.caption.lineHeight / t.caption.size,
      4,
    )
  })

  it('reaches the token h1 size at the largest breakpoint', () => {
    // responsiveFontSizes caps at the theme size: h1 28px = 1.75rem at the
    // largest breakpoint (1440px). NOTE: design doc §3.3 says h1 -> 32px at
    // >=1024px, which cannot hold with the 28px token — flagged in report.
    const h1 = muiTheme.typography.h1 as unknown as Record<string, unknown>
    const atLargest = h1['@media (min-width:1440px)'] as { fontSize?: string } | undefined
    expect(atLargest?.fontSize).toBe('1.75rem')
  })
})

/**
 * Swiss anchor regression — task/FE-02-swiss-style (2026-11-21, Lam D-F1:
 * no self-guessed info blue #1565C0; one accent only, International Orange
 * #FF4F00; old brand green #2E7D32 is semantic success only).
 */
describe('muiTheme — Swiss anchor', () => {
  it('uses the single Swiss accent #FF4F00 as primary', () => {
    expect(muiTheme.palette.primary.main).toBe('#FF4F00')
    expect(muiTheme.palette.primary.main).toBe(tokens.color.accent)
  })

  it('uses dark text on the accent, not white (contrast rule)', () => {
    // Trắng trên #FF4F00 chỉ 3.30:1 (FAIL 4.5:1); #1A1C1A đạt 5.20:1.
    expect(muiTheme.palette.primary.contrastText).toBe('#1A1C1A')
    expect(muiTheme.palette.primary.contrastText).toBe(tokens.color.onAccent)
    expect(muiTheme.palette.primary.contrastText).not.toBe('#FFFFFF')
  })

  it('has one accent only: secondary === primary', () => {
    expect(muiTheme.palette.secondary.main).toBe(muiTheme.palette.primary.main)
    expect(muiTheme.palette.secondary.contrastText).toBe(
      muiTheme.palette.primary.contrastText,
    )
  })

  it('keeps the old brand green as semantic success only', () => {
    expect(muiTheme.palette.success.main).toBe('#2E7D32')
    expect(muiTheme.palette.success.main).toBe(tokens.color.success)
    expect(muiTheme.palette.success.main).not.toBe(muiTheme.palette.primary.main)
  })

  it('maps info to the accent — no blue anywhere', () => {
    expect(muiTheme.palette.info.main).toBe('#FF4F00')
    expect(muiTheme.palette.info.main).toBe(muiTheme.palette.primary.main)
  })

  it('contains no banned blue #1565C0 anywhere in the palette', () => {
    const banned = '#1565C0'
    const walk = (v: unknown): void => {
      if (typeof v === 'string') {
        expect(v.toUpperCase()).not.toBe(banned)
      } else if (Array.isArray(v)) {
        v.forEach(walk)
      } else if (v !== null && typeof v === 'object') {
        Object.values(v).forEach(walk)
      }
    }
    walk(muiTheme.palette)
  })
})
