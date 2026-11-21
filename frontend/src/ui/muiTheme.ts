/**
 * MUI theme — tạo từ tokens.ts duy nhất, không nhân đôi hex vào file này.
 * Design doc §3.2 (palette + contrast đã kiểm chứng), §3.3 (typography,
 * shape, spacing, breakpoints, elevation, z-index), §3.4 (component
 * overrides), §3.7 (cssVariables: true để chuẩn bị dark mode sau này).
 *
 * SWISS ANCHOR — frontend-design skill (Ilm-Alan), 2026-11-21
 * (task/FE-02-swiss-style). Accent duy nhất = International Orange #FF4F00;
 * xanh lá #2E7D32 chỉ là semantic success; KHÔNG còn màu xanh nào (info =
 * accent, xem palette.info). Chữ trên accent là chữ tối #1A1C1A (trắng trên
 * #FF4F00 chỉ 3.30:1, FAIL 4.5:1; tối đạt 5.20:1).
 *
 * Chỉ dùng trên H5 (cần DOM thật). Không bao giờ import vào build weapp —
 * adapter layer §8.2 + platform file ép điều này (ESLint).
 */
import { createTheme, responsiveFontSizes } from '@mui/material/styles'
import type { ThemeOptions as MuiThemeOptions } from '@mui/material/styles'
import { tokens } from './tokens'

const c = tokens.color
const t = tokens.typography
/**
 * `responsiveFontSizes` (§3.3, bắt buộc theo design doc) ném MUI error #6
 * ("Unsupported non-unitless line height") khi lineHeight không phải số
 * không đơn vị. Tokens §3.3 cho line-height theo px (vd h1 36px) nên đổi
 * sang tỉ lệ không đơn vị (lh / size) — chiều cao dòng render ra ở cỡ chữ
 * gốc vẫn đúng bằng token px.
 */
const unitlessLineHeight = (size: number, lineHeight: number): number =>
  Math.round((lineHeight / size) * 10000) / 10000


declare module '@mui/material/styles' {
  interface Theme {
    imsf: {
      status: Record<
        'completed' | 'processing' | 'needsReview' | 'failed',
        { bg: string; text: string; icon: string; label: string }
      >
      container: {
        primary: string
        secondary: string
        success: string
        error: string
        warning: string
        surfaceVariant: string
      }
      outline: string
    }
  }
  interface ThemeOptions {
    imsf?: Theme['imsf']
  }
}

const themeOptions: MuiThemeOptions = {
  // §3.7: đặt cssVariables: true ngay từ GĐ1 (điều kiện tiên quyết cho dark
  // mode sau này), dù GĐ1 chỉ ship light.
  cssVariables: true,
  palette: {
    mode: 'light',
    // SWISS: MỘT accent duy nhất — MUI primary CHÍNH LÀ accent
    // (International Orange #FF4F00). contrastText là chữ tối #1A1C1A
    // (trắng trên accent chỉ 3.30:1, FAIL; tối đạt 5.20:1).
    primary: {
      main: c.accent,
      light: c.accentLight,
      dark: c.accentDark,
      contrastText: c.onAccent,
    },
    // secondary = primary, CỐ Ý — Swiss chỉ cho một accent; MUI bắt buộc
    // phải có slot secondary nên nó trỏ cùng accent, không phải màu thứ hai.
    secondary: {
      main: c.accent,
      light: c.accentLight,
      dark: c.accentDark,
      contrastText: c.onAccent,
    },
    error: {
      main: c.error,
      light: c.errorLight,
      dark: c.errorDark,
      contrastText: c.white, // trắng trên #D32F2F = 4.98:1 (PASS)
    },
    warning: {
      main: c.warning,
      light: c.warningLight,
      dark: c.warningDark,
      contrastText: c.white, // trắng trên #B45309 = 5.02:1 (PASS)
    },
    // success = xanh lá #2E7D32 (semantic, KHÔNG phải accent). Trắng trên
    // #2E7D32 = 5.13:1 (PASS).
    success: {
      main: c.success,
      light: c.successLight,
      dark: c.successDark,
      contrastText: c.white,
    },
    // info KHÔNG phải một màu — nó là alias của accent (Swiss: không có
    // màu xanh nào). Alert severity="info" / Toast kind="info" render cam
    // + icon, không bao giờ xanh. Token #1565C0 đã xoá (D-F1, Lam cấm).
    info: {
      main: c.accent,
      light: c.accentContainer,
      dark: c.accentDark,
      contrastText: c.onAccent,
    },
    background: { default: c.background, paper: c.surface },
    text: {
      primary: c.onSurface,
      secondary: c.onSurfaceVariant,
      disabled: c.textDisabled,
    },
    divider: c.divider,
    action: {
      active: tokens.action.active,
      hover: tokens.action.hover,
      selected: tokens.action.selected,
      disabled: tokens.action.disabled,
      disabledBackground: tokens.action.disabledBackground,
      focus: tokens.action.focus,
    },
  },
  typography: {
    fontFamily: tokens.font.family,
    htmlFontSize: tokens.font.baseSize,
    fontSize: tokens.font.baseSize,
    h1: { fontSize: t.h1.size, lineHeight: unitlessLineHeight(t.h1.size, t.h1.lineHeight), fontWeight: t.h1.weight },
    h2: { fontSize: t.h2.size, lineHeight: unitlessLineHeight(t.h2.size, t.h2.lineHeight), fontWeight: t.h2.weight },
    h3: { fontSize: t.h3.size, lineHeight: unitlessLineHeight(t.h3.size, t.h3.lineHeight), fontWeight: t.h3.weight },
    h4: { fontSize: t.h4.size, lineHeight: unitlessLineHeight(t.h4.size, t.h4.lineHeight), fontWeight: t.h4.weight },
    subtitle1: { fontSize: t.subtitle1.size, lineHeight: unitlessLineHeight(t.subtitle1.size, t.subtitle1.lineHeight), fontWeight: t.subtitle1.weight },
    subtitle2: { fontSize: t.subtitle2.size, lineHeight: unitlessLineHeight(t.subtitle2.size, t.subtitle2.lineHeight), fontWeight: t.subtitle2.weight },
    body1: { fontSize: t.body1.size, lineHeight: unitlessLineHeight(t.body1.size, t.body1.lineHeight), fontWeight: t.body1.weight },
    body2: { fontSize: t.body2.size, lineHeight: unitlessLineHeight(t.body2.size, t.body2.lineHeight), fontWeight: t.body2.weight },
    button: {
      fontSize: t.button.size,
      lineHeight: unitlessLineHeight(t.button.size, t.button.lineHeight),
      fontWeight: t.button.weight,
      letterSpacing: t.button.letterSpacing,
      textTransform: 'none',
    },
    caption: { fontSize: t.caption.size, lineHeight: unitlessLineHeight(t.caption.size, t.caption.lineHeight), fontWeight: t.caption.weight },
    overline: {
      fontSize: t.overline.size,
      lineHeight: unitlessLineHeight(t.overline.size, t.overline.lineHeight),
      fontWeight: t.overline.weight,
      letterSpacing: t.overline.letterSpacing,
    },
  },
  shape: { borderRadius: tokens.shape.base },
  spacing: tokens.spacing.unit,
  breakpoints: {
    values: {
      xs: tokens.breakpoints.xs,
      sm: tokens.breakpoints.sm,
      md: tokens.breakpoints.md,
      lg: tokens.breakpoints.lg,
      xl: tokens.breakpoints.xl,
    },
  },
  zIndex: {
    mobileStepper: 1000,
    fab: tokens.zIndex.fab,
    speedDial: 1050,
    appBar: tokens.zIndex.bottomNavigation, // bottomNavigation = appBar (§3.3)
    drawer: tokens.zIndex.drawer,
    modal: tokens.zIndex.modal,
    snackbar: tokens.zIndex.snackbar,
    tooltip: tokens.zIndex.tooltip,
  },
  imsf: {
    status: tokens.status,
    container: {
      primary: c.accentContainer,
      secondary: c.accentContainer,
      success: c.successContainer,
      error: c.errorContainer,
      warning: c.warningContainer,
      surfaceVariant: c.surfaceVariant,
    },
    outline: c.outline,
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        html: { '-webkit-text-size-adjust': '100%' },
        // Focus-visible ring 2px + offset 2px trên mọi phần tử tương tác (§3.4).
        '*:focus-visible': {
          outline: `2px solid ${c.accentDark}`,
          outlineOffset: '2px',
        },
        // Reduced motion: tắt mọi animation không cần thiết (§3.4).
        '@media (prefers-reduced-motion: reduce)': {
          '*, *::before, *::after': {
            animationDuration: '0.01ms !important',
            animationIterationCount: '1 !important',
            transitionDuration: '0.01ms !important',
          },
        },
      },
    },
    MuiButton: {
      defaultProps: { disableElevation: true },
      // MUI v9: `variants` nằm cùng cấp với styleOverrides (không nằm trong nó).
      variants: [
        {
          props: { variant: 'contained', color: 'primary' },
          style: {
            backgroundColor: c.accent,
            color: c.onAccent,
            '&:hover': { backgroundColor: c.accentDark },
            '&.Mui-disabled': {
              backgroundColor: tokens.action.disabledBackground,
              color: tokens.action.disabled,
            },
          },
        },
        {
          props: { variant: 'outlined', color: 'primary' },
          style: {
            border: `1.5px solid ${c.accent}`,
            color: c.accent,
            backgroundColor: 'transparent',
            '&:hover': { backgroundColor: tokens.action.hover, border: `1.5px solid ${c.accent}` },
          },
        },
        {
          props: { variant: 'text', color: 'primary' },
          style: {
            '&:hover': { backgroundColor: tokens.action.hover },
          },
        },
      ],
      styleOverrides: {
        root: {
          borderRadius: tokens.shape.button,
          minHeight: tokens.size.buttonMinHeight,
          textTransform: 'none',
          '&.Mui-focusVisible': {
            outline: `2px solid ${c.accentDark}`,
            outlineOffset: '2px',
          },
        },
        sizeLarge: { paddingLeft: 24, paddingRight: 24 },
        sizeMedium: { paddingLeft: 16, paddingRight: 16 },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: {
          borderRadius: tokens.shape.chip,
          height: tokens.size.chipHeight,
          fontSize: 12,
          fontWeight: 500,
        },
        icon: { fontSize: 16 },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: tokens.shape.card,
          boxShadow: tokens.elevation[1],
        },
      },
    },
    MuiCardContent: {
      styleOverrides: {
        root: {
          padding: 16,
          '&:last-child': { paddingBottom: 16 },
        },
      },
    },
    MuiTextField: {
      defaultProps: { variant: 'outlined' },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: {
          borderRadius: tokens.shape.textField,
          height: tokens.size.textFieldHeight,
          '& .MuiOutlinedInput-notchedOutline': { borderColor: c.outline },
          '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: c.outline },
          '&.Mui-focused .MuiOutlinedInput-notchedOutline': {
            borderColor: c.accent,
            borderWidth: 2,
          },
          '&.Mui-error .MuiOutlinedInput-notchedOutline': { borderColor: c.error },
        },
        input: {
          fontSize: 16, // tránh iOS tự zoom khi focus (§3.4)
        },
      },
    },
    MuiInputLabel: {
      styleOverrides: {
        root: { fontSize: 14, color: c.onSurfaceVariant },
      },
    },
    MuiBottomNavigation: {
      styleOverrides: {
        root: {
          height: `calc(${tokens.size.navHeight}px + env(safe-area-inset-bottom))`,
          paddingBottom: 'env(safe-area-inset-bottom)',
          backgroundColor: c.surface,
          borderTop: `1px solid ${c.divider}`,
        },
      },
    },
    MuiLinearProgress: {
      styleOverrides: {
        root: {
          height: 4,
          borderRadius: 2,
          backgroundColor: tokens.action.hover,
        },
        bar: { backgroundColor: c.accent },
      },
    },
    MuiCircularProgress: {
      styleOverrides: {
        root: { color: c.accent },
      },
    },
    MuiDialog: {
      styleOverrides: {
        paper: {
          borderRadius: tokens.shape.dialog,
          boxShadow: tokens.elevation[8],
        },
      },
    },
    MuiSnackbarContent: {
      styleOverrides: {
        root: {
          backgroundColor: c.onSurface,
          color: c.onAccent,
          borderRadius: tokens.shape.toast,
        },
        action: { color: c.accentContainer },
      },
    },
    MuiSkeleton: {
      styleOverrides: {
        root: { borderRadius: tokens.shape.skeleton },
      },
    },
    MuiFab: {
      styleOverrides: {
        root: {
          width: tokens.size.fab,
          height: tokens.size.fab,
          backgroundColor: c.accent,
          color: c.onAccent,
          boxShadow: tokens.elevation.fab,
          '&:hover': { backgroundColor: c.accentDark },
        },
      },
    },
    MuiSwitch: {
      styleOverrides: {
        switchBase: {
          '&.Mui-checked': { color: c.accent },
          '&.Mui-checked + .MuiSwitch-track': { backgroundColor: c.accent },
        },
      },
    },
  },
}

const baseTheme = createTheme(themeOptions)
// Elevation — chỉ dùng 0 / 1 / 2 / 4 / 8 (§3.3); ghi đè các mức dùng tới.
baseTheme.shadows[1] = tokens.elevation[1]
baseTheme.shadows[2] = tokens.elevation[2]
baseTheme.shadows[4] = tokens.elevation[4]
baseTheme.shadows[8] = tokens.elevation[8]

export const muiTheme = responsiveFontSizes(baseTheme)
export default muiTheme
