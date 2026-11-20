/**
 * TextField — props dùng chung cho cả 2 platform (design doc §8.2).
 * type 'number' + inputMode 'decimal' dùng cho các ô số (数量/单价).
 */
export type TextFieldType = 'text' | 'number' | 'password'
export type TextFieldInputMode = 'text' | 'decimal' | 'numeric' | 'tel' | 'email'

export interface TextFieldProps {
  label: string
  value: string
  onChange: (value: string) => void
  type?: TextFieldType
  inputMode?: TextFieldInputMode
  placeholder?: string
  error?: string
  helperText?: string
  disabled?: boolean
  maxLength?: number
  ariaLabel?: string
}

export default TextFieldProps
