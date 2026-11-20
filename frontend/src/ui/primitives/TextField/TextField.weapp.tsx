/**
 * TextField — WeChat Mini Program (NutUI React 3.0.20 Input).
 * NutUI Input không có floating label: label render phía trên, error /
 * helper phía dưới, theo tokens (§3.1).
 */
import { View, Text } from '@tarojs/components'
import { Input as NutInput } from '@nutui/nutui-react-taro'
import { tokens } from '../../tokens'
import type { TextFieldProps } from './TextField.types'

export default function TextField(props: TextFieldProps) {
  const {
    label,
    value,
    onChange,
    type = 'text',
    placeholder,
    error,
    helperText,
    disabled,
    maxLength,
  } = props
  const nutType = type === 'number' ? 'digit' : type
  return (
    <View>
      <Text
        style={{
          display: 'block',
          fontSize: tokens.typography.subtitle2.size,
          fontWeight: tokens.typography.subtitle2.weight,
          color: tokens.color.onSurface,
          marginBottom: 4,
        }}
      >
        {label}
      </Text>
      <NutInput
        type={nutType}
        value={value}
        placeholder={placeholder}
        disabled={disabled}
        maxLength={maxLength}
        onChange={(v: string) => onChange(v)}
      />
      {error ? (
        <Text
          style={{
            display: 'block',
            fontSize: tokens.typography.caption.size,
            color: tokens.color.error,
            marginTop: 4,
          }}
        >
          {error}
        </Text>
      ) : helperText ? (
        <Text
          style={{
            display: 'block',
            fontSize: tokens.typography.caption.size,
            color: tokens.color.onSurfaceVariant,
            marginTop: 4,
          }}
        >
          {helperText}
        </Text>
      ) : null}
    </View>
  )
}
