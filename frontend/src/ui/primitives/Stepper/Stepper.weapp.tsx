/**
 * Stepper — WeChat Mini Program (NutUI React 3.0.20 InputNumber).
 */
import { InputNumber as NutInputNumber } from '@nutui/nutui-react-taro'
import type { StepperProps } from './Stepper.types'

export default function Stepper(props: StepperProps) {
  const { value, onChange, min = 0, max, step = 1, digits, disabled } = props
  // NutUI gộp props bằng spread trên defaultProps (max: 9999, digits: 0):
  // truyền max={undefined} / digits={undefined} sẽ GHI ĐÈ default thành
  // undefined → Number(max) = NaN → input hiển thị NaN. Chỉ truyền khi có giá trị.
  return (
    <NutInputNumber
      value={value}
      min={min}
      step={step}
      disabled={disabled}
      {...(max !== undefined ? { max } : {})}
      {...(digits !== undefined ? { digits } : {})}
      onChange={(v: number | string) => onChange(Number(v))}
    />
  )
}
