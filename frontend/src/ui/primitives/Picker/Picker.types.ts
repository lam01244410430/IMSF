/**
 * Picker — props dùng chung (design doc §8.2).
 * Một cột duy nhất (GĐ1 chỉ cần chọn đơn vị / hộ gia đình).
 */
export interface PickerOption {
  label: string | number
  value: string | number
}

export interface PickerProps {
  visible: boolean
  title?: string
  options: PickerOption[]
  value: string | number | null
  onConfirm: (value: string | number) => void
  onCancel: () => void
}

export default PickerProps
