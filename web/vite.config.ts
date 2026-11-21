import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    // SVGs must be emitted as files, not inlined as data: URIs:
    // <use href="data:..."> does not render in Chromium, while
    // <use href="/assets/*.svg"> (same-origin file) does.
    assetsInlineLimit: 0,
  },
})
