/**
 * Stepper — props dùng chung cho cả 2 platform (design doc §8.2).
 * Dùng cho ô 数量 trong ReceiptLineEditor (§5.3).
 */
export interface StepperProps {
  value: number
  onChange: (value: number) => void
  min?: number
  max?: number
  step?: number
  digits?: number
  disabled?: boolean
  ariaLabel?: string
}

export default StepperProps
