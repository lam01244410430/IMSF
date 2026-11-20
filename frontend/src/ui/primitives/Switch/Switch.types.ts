/**
 * Switch — props dùng chung (design doc §8.2).
 * Dùng cho toggle is_stock_item trong ReceiptLineEditor (§5.3).
 */
export interface SwitchProps {
  checked: boolean
  onChange: (checked: boolean) => void
  disabled?: boolean
  ariaLabel?: string
}

export default SwitchProps
