/**
 * IMSF-v2 Tokens — NGUỒN CHÂN LÝ DUY NHẤT cho mọi giá trị màu / spacing / radius.
 * Design doc §3.1 (IMSF-v2 Tokens từ Figma), §3.2 (palette + contrast), §3.3
 * (typography, shape, spacing, breakpoints, elevation, z-index).
 *
 * QUY TẮC: một giá trị hex chỉ tồn tại ở đúng một chỗ — file này. Mọi nơi khác
 * (muiTheme.ts, tokens.css, nutui.css sinh ra) đều đọc từ đây. ESLint cấm
 * hex literal ngoài src/ui/**.
 *
 * GHI CHÚ GATE 0 (2026-11-21, kiểm chứng trên @nutui/nutui-react-taro@3.0.20
 * đã cài, file dist/styles/variables.scss — 862 biến --nutui-*):
 * - `--nutui-color-text-secondary` KHÔNG tồn tại (doc §3.6 ghi ✅ là sai);
 *   slot text phụ của NutUI là `--nutui-color-text-help` (mặc định #888b94).
 * - `--nutui-base-font-size` KHÔNG tồn tại; slot cỡ chữ gốc là
 *   `--nutui-font-size-base` (mặc định 14px).
 * - `--nutui-border-radius-base` KHÔNG tồn tại; radius đặt theo từng
 *   component (vd `--nutui-button-border-radius` — đã xác nhận tồn tại).
 * - `--nutui-color-primary-light` KHÔNG tồn tại (chỉ có
 *   `--nutui-color-primary-light-pressed`).
 * - `--nutui-font-family` KHÔNG phải CSS var (chỉ là SCSS var $font-family);
 *   font stack đặt trên phần tử root của app thay vì qua biến NutUI.
 * - `--nutui-brand-color` không tồn tại (đúng như doc §3.6 ghi ❌).
 *
 * File này chỉ dùng cú pháp TypeScript "erasable" (không enum, không
 * namespace, không parameter property) để scripts/build-tokens.mjs có thể
 * import trực tiếp bằng Node 22 type-stripping.
 */

export const tokens = {
  color: {
    primary: '#2E7D32',
    onPrimary: '#FFFFFF',
    primaryContainer: '#C8E6C9',
    onPrimaryContainer: '#1B5E20',
    secondary: '#FF8F00',
    secondaryContainer: '#FFE0B2',
    error: '#D32F2F',
    errorContainer: '#FCE8E6',
    warning: '#B45309',
    warningContainer: '#FFF3E0',
    surface: '#FFFFFF',
    background: '#F7F8F7',
    surfaceVariant: '#E8EDE8',
    outline: '#79747E',
    onSurface: '#1A1C1A',
    onSurfaceVariant: '#5F6368',
    // Giá trị suy ra (§3.2 — không phải token Figma, ghi rõ là suy ra):
    primaryLight: '#4CAF50', // Material Green 500
    primaryDark: '#1B5E20', // Material Green 900 = onPrimaryContainer (cố ý)
    secondaryLight: '#FFA726', // Material Amber 400
    secondaryDark: '#EF6C00', // Material Orange 800
    errorLight: '#EF5350', // Material Red 400
    errorDark: '#B71C1C', // Material Red 900
    warningLight: '#F59E0B', // chỉ dùng cho icon/background, không làm text trên trắng
    warningDark: '#92400E',
    // ★ TOKEN MỚI, không có trong Figma — cần Lam duyệt (doc §10.2 D-F1).
    // Chưa component nào dùng màu info; nếu Lam không duyệt thì info state
    // fallback sang primary + icon, không thêm màu xanh nào khác.
    info: '#1565C0',
    infoLight: '#E3F2FD',
    infoDark: '#0D47A1',
    textDisabled: 'rgba(26,28,26,0.38)',
    divider: '#E8EDE8', // = surfaceVariant; chỉ làm hairline
  },
  action: {
    active: 'rgba(26,28,26,0.54)',
    hover: 'rgba(46,125,50,0.08)',
    selected: 'rgba(46,125,50,0.12)',
    disabled: 'rgba(26,28,26,0.38)',
    disabledBackground: 'rgba(26,28,26,0.12)',
    focus: 'rgba(46,125,50,0.12)',
  },
  font: {
    family:
      '"Noto Sans SC", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Source Han Sans SC", system-ui, -apple-system, "Segoe UI", sans-serif',
    baseSize: 16,
    baseLineHeight: 1.5,
  },
  typography: {
    h1: { size: 28, lineHeight: 36, weight: 700 },
    h2: { size: 24, lineHeight: 32, weight: 700 },
    h3: { size: 20, lineHeight: 28, weight: 700 },
    h4: { size: 18, lineHeight: 26, weight: 700 },
    subtitle1: { size: 16, lineHeight: 24, weight: 500 },
    subtitle2: { size: 14, lineHeight: 20, weight: 500 },
    body1: { size: 16, lineHeight: 24, weight: 400 },
    body2: { size: 14, lineHeight: 20, weight: 400 },
    button: { size: 14, lineHeight: 20, weight: 500, letterSpacing: '0.02em' },
    caption: { size: 12, lineHeight: 16, weight: 400 },
    overline: { size: 12, lineHeight: 16, weight: 500, letterSpacing: '0.08em' },
  },
  shape: {
    base: 12,
    button: 20,
    buttonSmall: 16,
    card: 16,
    textField: 12,
    chip: 8,
    dialog: 20,
    toast: 12,
    skeleton: 12,
    fab: '50%',
  },
  spacing: {
    unit: 8,
    scale: [4, 8, 12, 16, 24, 32, 48, 64],
    pagePaddingMobile: 16,
    pagePaddingDesktop: 24,
    gap: 12,
    minTouchGap: 8,
  },
  breakpoints: {
    xs: 0,
    sm: 768,
    md: 1024,
    lg: 1440,
    xl: 1920,
    containerMaxWidthMd: 1120,
    containerMaxWidthLg: 1280,
  },
  elevation: {
    1: '0 1px 2px rgba(26,28,26,0.08)',
    2: '0 2px 8px rgba(26,28,26,0.10)',
    4: '0 4px 16px rgba(26,28,26,0.12)',
    8: '0 8px 24px rgba(26,28,26,0.16)',
    fab: '0 6px 16px rgba(46,125,50,0.35)',
  },
  zIndex: {
    bottomNavigation: 1100,
    fab: 1120,
    drawer: 1200,
    modal: 1300,
    snackbar: 1400,
    tooltip: 1500,
  },
  size: {
    headerHeight: 56,
    navHeight: 56,
    fab: 56,
    buttonMinHeight: 48,
    textFieldHeight: 56,
    chipHeight: 28,
    receiptRowHeight: 72,
  },
  /** Chip trạng thái receipt (§3.4) — luôn icon + text, không bao giờ chỉ màu. */
  status: {
    completed: { bg: '#C8E6C9', text: '#1B5E20', icon: 'CheckCircle', label: '已完成' },
    processing: { bg: '#FFF3E0', text: '#B45309', icon: 'HourglassTop', label: '处理中' },
    needsReview: { bg: '#FFE0B2', text: '#1A1C1A', icon: 'FactCheck', label: '需核对' },
    failed: { bg: '#FCE8E6', text: '#D32F2F', icon: 'Error', label: '识别失败' },
  },
  /**
   * Namespace riêng cho NutUI (§3.6: biến chỉ NutUI mới có, MUI bỏ qua).
   * Giá trị ở đây vẫn là token IMSF, chỉ khác tên biến đích.
   */
  nutui: {
    cellPadding: '12px 16px',
  },
} as const

export type Tokens = typeof tokens
