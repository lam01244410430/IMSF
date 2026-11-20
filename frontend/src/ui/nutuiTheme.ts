/**
 * NutUI theme wiring — design doc §3.6 + §8.2.
 *
 * Cơ chế chính là override CSS-variable trong stylesheet cấp app
 * (src/ui/nutui.css, sinh từ tokens.ts) — KHÔNG dùng prop `theme` của
 * ConfigProvider cho bất cứ gì ở GĐ1 (hình dạng prop runtime theming đã xác
 * nhận tồn tại, nhưng stylesheet override là cơ chế chính theo doc).
 *
 * File này chỉ export locale zh-CN cho ConfigProvider (đã xác nhận tồn tại
 * trong @nutui/nutui-react-taro@3.0.20: dist/es/locales/zh-CN).
 */
import zhCN from '@nutui/nutui-react-taro/dist/es/locales/zh-CN'

export const nutuiLocale = zhCN
export default nutuiLocale
