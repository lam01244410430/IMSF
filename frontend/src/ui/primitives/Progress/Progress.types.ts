/**
 * Progress — props dùng chung (design doc §8.2).
 * value undefined = indeterminate (đang chạy, không biết %).
 */
export interface ProgressProps {
  /** 0–100. undefined = indeterminate. */
  value?: number
  ariaLabel?: string
}

export default ProgressProps
