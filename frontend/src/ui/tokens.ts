/**
 * IMSF-v2 Tokens — NGUỒN CHÂN LÝ DUY NHẤT cho mọi giá trị màu / spacing / radius.
 * Design doc §3.1 (IMSF-v2 Tokens từ Figma), §3.2 (palette + contrast), §3.3
 * (typography, shape, spacing, breakpoints, elevation, z-index).
 *
 * SWISS ANCHOR — frontend-design skill (Ilm-Alan), áp dụng 2026-11-21
 * (task/FE-02-swiss-style; Lam: "không dùng màu xanh tự đoán, sử dụng phong
 * cách https://github.com/Ilm-Alan/frontend-design"). Swiss = mặt trắng
 * #FFFFFF / trung tính #F7F7F8 + sans + hairline 1px + MỘT accent duy nhất
 * (International Orange #FF4F00), dùng có chủ ý. Xanh lá thương hiệu cũ
 * #2E7D32 giờ chỉ là màu semantic success. Không còn màu xanh nào trong theme.
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
    // ★ SWISS ACCENT — International Orange #FF4F00 (token Swiss, chính xác).
    // Swiss Red #E4002B sẽ đụng màu error; Yves Klein Blue #002FA7 là một
    // màu xanh khác (Lam vừa cấm xanh tự đoán). Secondary cam cũ #FF8F00
    // được thay bằng token Swiss chính xác.
    accent: '#FF4F00',
    // Chữ trắng trên #FF4F00 = 3.30:1 (FAIL 4.5:1) — contrastText phải là
    // chữ tối. #1A1C1A trên #FF4F00 = 5.20:1 (PASS).
    onAccent: '#1A1C1A',
    accentLight: '#FFA726', // Material Orange 400 (cam sáng kề accent)
    accentDark: '#EF6C00', // Material Orange 800 (cam tối kề accent)
    accentContainer: '#FFE0B2', // container cam nhạt (giữ giá trị Figma)
    onAccentContainer: '#1A1C1A', // #FFE0B2 vs #1A1C1A = 13.52:1
    // Xanh lá thương hiệu cũ #2E7D32 giờ CHỈ là màu SEMANTIC success
    // (completed / success), KHÔNG còn là màu action chính.
    success: '#2E7D32',
    successLight: '#4CAF50', // Material Green 500
    successDark: '#1B5E20', // Material Green 900
    successContainer: '#C8E6C9',
    onSuccessContainer: '#1B5E20', // #C8E6C9 vs #1B5E20 = 5.85:1
    // SEMANTIC error / warning — token chức năng, KHÔNG phải accent
    // thương hiệu. Anchor Swiss không định nghĩa màu semantic; ghi rõ tách
    // biệt khỏi accent.
    error: '#D32F2F',
    errorContainer: '#FCE8E6',
    warning: '#B45309',
    warningContainer: '#FFF3E0',
    // MẶT SWISS — trắng tinh + trung tính #F7F7F8 (token anchor, chính xác).
    surface: '#FFFFFF',
    // Trắng tinh, dùng làm chữ tương phản trên các màu semantic tối
    // (error/warning/success). Cùng giá trị với surface nhưng đặt tên riêng
    // để muiTheme không phải hardcode hex (ESLint cấm hex ngoài tokens.ts).
    white: '#FFFFFF',
    background: '#F7F7F8',
    // Xám trung tính cho hairline — Swiss neutral tối đi 8% theo công thức
    // (trộn #F7F7F8 với đen 8%: 247/247/248 → 227/227/228 = #E3E3E4).
    // Thay xám pha xanh cũ #E8EDE8; = divider.
    surfaceVariant: '#E3E3E4',
    outline: '#79747E',
    onSurface: '#1A1C1A',
    onSurfaceVariant: '#5F6368',
    // Giá trị suy ra (không phải token Figma, ghi rõ là suy ra):
    errorLight: '#EF5350', // Material Red 400
    errorDark: '#B71C1C', // Material Red 900
    warningLight: '#F59E0B', // chỉ dùng cho icon/background, không làm text trên trắng
    warningDark: '#92400E',
    // (info #1565C0 ĐÃ XOÁ 2026-11-21 — xanh tự đoán, Lam cấm. Info state
    // fallback sang accent + icon: muiTheme palette.info = accent,
    // --nutui-color-info = accent. Không còn màu xanh nào trong theme.)
    textDisabled: 'rgba(26,28,26,0.38)',
    divider: '#E3E3E4', // = surfaceVariant; chỉ làm hairline
  },
  action: {
    active: 'rgba(26,28,26,0.54)',
    hover: 'rgba(255,79,0,0.08)',
    selected: 'rgba(255,79,0,0.12)',
    disabled: 'rgba(26,28,26,0.38)',
    disabledBackground: 'rgba(26,28,26,0.12)',
    focus: 'rgba(255,79,0,0.12)',
  },
  font: {
    // SYSTEM FONTS ONLY (Lam 2026-11-21 13:19: "k dùng chuẩn của google vì
    // sẽ dễ bị chặn lại" — Google bị chặn ở TQ nên KHÔNG dùng web font).
    // Font lấy từ chính thiết bị người dùng: PingFang SC (iOS/macOS),
    // Hiragino Sans GB, Microsoft YaHei (Windows), system sans (Android),
    // rồi generic system-ui / sans-serif. KHÔNG fetch font từ Google hay
    // bất kỳ CDN nào nên GFW không chặn được. KHÔNG có tên font Google/Adobe
    // nào trong stack (không Noto, không Source Han) để tránh nhầm với
    // chuẩn Google. Khớp quyết định "system font fallbacks only" của
    // frontend v1. Ghi chú: Swiss anchor ghi Akzidenz/Helvetica/Söhne
    // (Latin, không có glyph CJK) — với app tiếng Trung, stack system
    // font CJK trên mới là sans mang anchor đó.
    family:
      '"PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", system-ui, -apple-system, "Segoe UI", sans-serif',
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
    fab: '0 6px 16px rgba(255,79,0,0.35)',
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
    completed: { bg: '#C8E6C9', text: '#1B5E20', icon: 'CheckCircle', label: '已完成' }, // = successContainer (semantic)
    processing: { bg: '#FFF3E0', text: '#B45309', icon: 'HourglassTop', label: '处理中' }, // = warningContainer
    needsReview: { bg: '#FFE0B2', text: '#1A1C1A', icon: 'FactCheck', label: '需核对' }, // = accentContainer
    failed: { bg: '#FCE8E6', text: '#D32F2F', icon: 'Error', label: '识别失败' }, // = errorContainer
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
