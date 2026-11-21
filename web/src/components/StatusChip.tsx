/**
 * Status chip — text + a text glyph, NEVER colour alone (plan §5.4).
 *
 * Contrast (measured, WCAG relative luminance):
 * - error:   text #B71C1C on bg #FCE8E6 = 5.58:1 (PASS ≥ 4.5:1)
 *   — this is the FIX for the known gap: #D32F2F on #FCE8E6 was 4.23:1.
 *   Background kept, text darkened one step (#D32F2F → #B71C1C).
 * - warning: text #B45309 on bg #FFF7ED = 4.73:1 (PASS)
 * - success: text #2E7D32 on bg #E8F5E9 = 4.56:1 (PASS)
 * - accent:  text #C2410C on bg #FDEDE8 = 4.55:1 (PASS)
 * - neutral: text #5F6368 on bg #F7F7F8 = 5.65:1 (PASS)
 *
 * Dark pairs (Dashboard Phase A, same variables, dark values):
 * - error:   text #FF8A80 on bg #2E1B19 = 7.15:1 (PASS)
 * - warning: text #F59E0B on bg #2E2410 = 7.11:1 (PASS)
 * - success: text #4CAF50 on bg #1C2B1E = 5.34:1 (PASS)
 * - accent:  text #F97316 on bg #33200F = 5.53:1 (PASS)
 * - neutral: text #A8AFA9 on bg #2A2E2C = 6.14:1 (PASS)
 */
export type ChipTone = 'error' | 'warning' | 'success' | 'accent' | 'neutral'

const TONE_GLYPH: Record<ChipTone, string> = {
  error: '×',
  warning: '!',
  success: '✓',
  accent: '•',
  neutral: '•',
}

export function StatusChip({
  tone,
  label,
  title,
}: {
  tone: ChipTone
  label: string
  title?: string
}) {
  return (
    <span className={`status-chip status-chip-${tone}`} title={title}>
      <span className="status-chip-glyph" aria-hidden="true">
        {TONE_GLYPH[tone]}
      </span>
      <span>{label}</span>
    </span>
  )
}
