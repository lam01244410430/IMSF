import { tokens } from './ui/tokens'

export default defineAppConfig({
  pages: [
    'pages/index/index'
  ],
  window: {
    backgroundTextStyle: 'light',
    navigationBarBackgroundColor: tokens.color.surface,
    navigationBarTitleText: 'WeChat',
    navigationBarTextStyle: 'black'
  }
})
