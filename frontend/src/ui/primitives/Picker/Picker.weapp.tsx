/**
 * Picker — WeChat Mini Program (NutUI React 3.0.20 Picker, 1 cột).
 */
import { Picker as NutPicker } from '@nutui/nutui-react-taro'
import type { PickerProps } from './Picker.types'

export default function Picker(props: PickerProps) {
  const { visible, options, value, onConfirm, onCancel } = props
  return (
    <NutPicker
      visible={visible}
      options={[options]}
      value={value !== null ? [value] : undefined}
      onConfirm={(_selectedOptions, selectedValue) => {
        const v = selectedValue[0]
        if (v !== null && v !== undefined) onConfirm(v)
      }}
      onCancel={() => onCancel()}
      onClose={() => onCancel()}
    />
  )
}
