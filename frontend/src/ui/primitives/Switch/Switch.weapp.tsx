/**
 * Switch — WeChat Mini Program (NutUI React 3.0.20 Switch).
 */
import { Switch as NutSwitch } from '@nutui/nutui-react-taro'
import type { SwitchProps } from './Switch.types'

export default function Switch(props: SwitchProps) {
  const { checked, onChange, disabled } = props
  return <NutSwitch checked={checked} disabled={disabled} onChange={(v: boolean) => onChange(v)} />
}
