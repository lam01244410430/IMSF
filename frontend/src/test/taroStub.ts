/**
 * Stub module cho alias '@tarojs/taro' trong vitest.config.ts.
 * Mọi import '@tarojs/taro' (kể cả từ bên trong node_modules ESM như NutUI)
 * đều resolve về file này, nên mock luôn áp dụng — vi.mock trong setup.ts
 * không chặn được import nội bộ của package ESM externalized.
 */
export * from './taroMock'
export { taroMock as default } from './taroMock'
