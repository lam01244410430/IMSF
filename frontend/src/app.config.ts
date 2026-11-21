import { tokens } from './ui/tokens'

/**
 * App config (§8.3, §4.1). Trang đầu = upload (launch page). navigationStyle
 * 'custom' — header tự render (§4.2). tabBar custom + FAB placeholder: slot
 * giữa trỏ lại upload (custom bar chặn tap; nếu custom bar lỗi, fallback về
 * trang chủ).
 */
export default defineAppConfig({
  pages: [
    'pages/upload/index',
    'pages/fridge/index',
    'pages/recipes/index',
    'pages/mine/index',
    'pages/login/index',
    'pages/receipts/index',
    'pages/receipt/index',
    'pages/transactions/index',
    'pages/spending/index',
  ],
  window: {
    backgroundTextStyle: 'light',
    navigationBarBackgroundColor: tokens.color.surface,
    navigationBarTitleText: 'IMSF-v2',
    navigationBarTextStyle: 'black',
    navigationStyle: 'custom',
  },
  tabBar: {
    custom: true,
    color: tokens.color.onSurfaceVariant,
    selectedColor: tokens.color.accent,
    backgroundColor: tokens.color.surface,
    list: [
      { pagePath: 'pages/upload/index', text: '首页' },
      { pagePath: 'pages/fridge/index', text: '冰箱' },
      { pagePath: 'pages/upload/index', text: '拍照' },
      { pagePath: 'pages/recipes/index', text: '菜谱' },
      { pagePath: 'pages/mine/index', text: '我的' },
    ],
  },
})
