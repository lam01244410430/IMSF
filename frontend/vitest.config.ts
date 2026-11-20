import { defineConfig } from 'vitest/config'
import { fileURLToPath } from 'node:url'

export default defineConfig({
  // Taro runtime đọc các global ENABLE_* do webpack DefinePlugin định nghĩa
  // khi build thật; trong Vitest chúng không tồn tại nên file runtime ESM nổ
  // ReferenceError ngay khi được load. Định nghĩa chúng ở đây (false = tắt
  // các API DOM mở rộng không cần trong test).
  define: {
    ENABLE_INNER_HTML: 'false',
    ENABLE_ADJACENT_HTML: 'false',
    ENABLE_CLONE_NODE: 'false',
    ENABLE_CONTAINS: 'false',
    ENABLE_MUTATION_OBSERVER: 'false',
    ENABLE_SIZE_APIS: 'false',
    ENABLE_TEMPLATE_CONTENT: 'false',
  },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      // Mọi import '@tarojs/taro' / '@tarojs/components' — kể cả từ bên
      // trong package ESM như NutUI — đều resolve về stub. vi.mock trong
      // setup.ts chỉ chặn được import resolve về cùng một file như test
      // file; NutUI import '@tarojs/components' về dist/esm/index.js (khác
      // file với main) nên mock bị bypass và runtime thật của Taro bị load
      // → ReferenceError ENABLE_INNER_HTML.
      '@tarojs/taro': fileURLToPath(new URL('./src/test/taroStub.ts', import.meta.url)),
      '@tarojs/components': fileURLToPath(
        new URL('./src/test/taroComponentsStub.tsx', import.meta.url),
      ),
      // Vitest (SSR) resolve 'main' → NutUI UMD bundle, trong đó lottie-web
      // chạy canvas detection ngay lúc load và nổ trên jsdom (không có
      // canvas). Webpack build thật resolve 'module' → bản ESM. Alias về
      // đúng entry ESM đó cho test.
      '@nutui/nutui-react-taro': fileURLToPath(
        new URL(
          './node_modules/@nutui/nutui-react-taro/dist/es/packages/nutui.react.build.js',
          import.meta.url,
        ),
      ),
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    // NutUI là ESM thuần: nếu để Vitest externalize (load bằng Node ESM
    // native), các import @tarojs/* BÊN TRONG NutUI không đi qua module
    // runner nên vi.mock ở setup.ts không chặn được. Inline các package này
    // để import của chúng đi qua runner (và nhận alias ở trên).
    server: {
      deps: {
        inline: [
          '@nutui/nutui-react-taro',
          '@nutui/icons-react-taro',
          '@tarojs/components',
          '@tarojs/taro',
        ],
      },
    },
  },
})
