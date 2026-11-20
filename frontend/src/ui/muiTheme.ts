/**
 * MUI theme — tạo từ tokens.ts duy nhất, không nhân đôi hex vào file này.
 * Design doc §3.2 (palette + contrast đã kiểm chứng), §3.3 (typography,
 * shape, spacing, breakpoints, elevation, z-index), §3.4 (component
 * overrides), §3.7 (cssVariables: true để chuẩn bị dark mode sau này).
 *
 * Chỉ dùng trên H5 (cần DOM thật). Không bao giờ import vào build weapp —
 * adapter layer §8.2 + platform file ép điều này (ESLint).
 */
import { createTheme, responsiveFontSizes } from '@mui/material/styles'
import type { ThemeOptions as MuiThemeOptions } from '@mui/material/styles'
import { tokens } from './tokens'

const c = tokens.color
const t = tokens.typography

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
    primary: {
      main: c.primary,
      light: c.primaryLight,
      dark: c.primaryDark,
      contrastText: c.onPrimary,
    },
    // §3.2: KHÔNG bao giờ chữ trắng trên secondary (fail 2.29:1) —
    // contrastText là #1A1C1A.
    secondary: {
      main: c.secondary,
      light: c.secondaryLight,
      dark: c.secondaryDark,
      contrastText: c.onSurface,
    },
    error: {
      main: c.error,
      light: c.errorLight,
      dark: c.errorDark,
      contrastText: c.onPrimary,
    },
    warning: {
      main: c.warning,
      light: c.warningLight,
      dark: c.warningDark,
      contrastText: c.onPrimary,
    },
    // = primary, cố ý — không thêm một xanh lá thứ hai (§3.2).
    success: {
      main: c.primary,
      light: c.primaryContainer,
      dark: c.primaryDark,
      contrastText: c.onPrimary,
    },
    // ★ Token mới (D-F1, chờ Lam duyệt). Chưa component nào dùng.
    info: {
      main: c.info,
      light: c.infoLight,
      dark: c.infoDark,
      contrastText: c.onPrimary,
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
    h1: { fontSize: t.h1.size, lineHeight: `${t.h1.lineHeight}px`, fontWeight: t.h1.weight },
    h2: { fontSize: t.h2.size, lineHeight: `${t.h2.lineHeight}px`, fontWeight: t.h2.weight },
    h3: { fontSize: t.h3.size, lineHeight: `${t.h3.lineHeight}px`, fontWeight: t.h3.weight },
    h4: { fontSize: t.h4.size, lineHeight: `${t.h4.lineHeight}px`, fontWeight: t.h4.weight },
    subtitle1: { fontSize: t.subtitle1.size, lineHeight: `${t.subtitle1.lineHeight}px`, fontWeight: t.subtitle1.weight },
    subtitle2: { fontSize: t.subtitle2.size, lineHeight: `${t.subtitle2.lineHeight}px`, fontWeight: t.subtitle2.weight },
    body1: { fontSize: t.body1.size, lineHeight: `${t.body1.lineHeight}px`, fontWeight: t.body1.weight },
    body2: { fontSize: t.body2.size, lineHeight: `${t.body2.lineHeight}px`, fontWeight: t.body2.weight },
    button: {
      fontSize: t.button.size,
      lineHeight: `${t.button.lineHeight}px`,
      fontWeight: t.button.weight,
      letterSpacing: t.button.letterSpacing,
      textTransform: 'none',
    },
    caption: { fontSize: t.caption.size, lineHeight: `${t.caption.lineHeight}px`, fontWeight: t.caption.weight },
    overline: {
      fontSize: t.overline.size,
      lineHeight: `${t.overline.lineHeight}px`,
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
      primary: c.primaryContainer,
      secondary: c.secondaryContainer,
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
          outline: `2px solid ${c.primaryDark}`,
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
            backgroundColor: c.primary,
            color: c.onPrimary,
            '&:hover': { backgroundColor: c.primaryDark },
            '&.Mui-disabled': {
              backgroundColor: tokens.action.disabledBackground,
              color: tokens.action.disabled,
            },
          },
        },
        {
          props: { variant: 'outlined', color: 'primary' },
          style: {
            border: `1.5px solid ${c.primary}`,
            color: c.primary,
            backgroundColor: 'transparent',
            '&:hover': { backgroundColor: tokens.action.hover, border: `1.5px solid ${c.primary}` },
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
            outline: `2px solid ${c.primaryDark}`,
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
            borderColor: c.primary,
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
        bar: { backgroundColor: c.primary },
      },
    },
    MuiCircularProgress: {
      styleOverrides: {
        root: { color: c.primary },
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
          color: c.onPrimary,
          borderRadius: tokens.shape.toast,
        },
        action: { color: c.primaryContainer },
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
          backgroundColor: c.primary,
          color: c.onPrimary,
          boxShadow: tokens.elevation.fab,
          '&:hover': { backgroundColor: c.primaryDark },
        },
      },
    },
    MuiSwitch: {
      styleOverrides: {
        switchBase: {
          '&.Mui-checked': { color: c.primary },
          '&.Mui-checked + .MuiSwitch-track': { backgroundColor: c.primary },
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
