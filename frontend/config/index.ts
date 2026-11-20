import { defineConfig, type UserConfigExport } from '@tarojs/cli'
import TsconfigPathsPlugin from 'tsconfig-paths-webpack-plugin'
import devConfig from './dev'
import prodConfig from './prod'

// https://taro-docs.jd.com/docs/next/config#defineconfig-辅助函数
export default defineConfig<'webpack5'>(async (merge, { command: _command, mode: _mode }) => {
  const baseConfig: UserConfigExport<'webpack5'> = {
    projectName: 'frontend',
    date: '2026-11-20',
    designWidth: 750,
    deviceRatio: {
      640: 2.34 / 2,
      750: 1,
      375: 2,
      828: 1.81 / 2
    },
    sourceRoot: 'src',
    outputRoot: 'dist',
    plugins: [
      "@tarojs/plugin-generator"
    ],
    defineConstants: {
    },
    /**
     * Default rỗng cho TARO_APP_API_BASE_URL (§8.4) — fix crash H5 2026-11-21.
     *
     * Khi biến này không có trong bất kỳ file `.env*` nào, Taro không định
     * nghĩa `process.env.TARO_APP_API_BASE_URL` cho DefinePlugin, nên biểu
     * thức còn nguyên trong bundle và browser ném `ReferenceError: process
     * is not defined` (browser không có `process`). Giá trị mặc định `'""'`
     * (chuỗi rỗng đã JSON-stringify) khiến DefinePlugin luôn thay thế nó.
     * An toàn khi có giá trị thật: `patchEnv` gộp theo thứ tự
     * `Object.assign({}, config.env, dotenv)` nên giá trị từ `.env*` /
     * `.env*.local` / CI secret GHI ĐÈ default này, không bao giờ bị mất.
     */
    env: {
      TARO_APP_API_BASE_URL: '""'
    },
    copy: {
      patterns: [
      ],
      options: {
      }
    },
    framework: 'react',
    compiler: 'webpack5',
    /**
     * Terser override — H5 production build fix (2026-11-21).
     *
     * Taro 4.3.3's H5 default Terser options set `output.quote_keys: true`.
     * With that flag, Terser 5.51.4 quotes private class field names, emitting
     * `#"e";` instead of `#e;` — a SyntaxError in every JS engine (V8 +
     * Chromium both reject it; verified with acorn at app.js 2:80049).
     * Any dependency using native private fields breaks the H5 bundle; here it
     * was @tanstack/query-core's `Mutation` class (`#client`, `#observers`,
     * `#mutationCache`, `#retryer`). The weapp build is NOT affected (its
     * mini defaults have no `quote_keys`, and all 14 weapp JS files parse).
     * `quote_keys: false` restores Terser's default behaviour; `keep_quoted_props`
     * (still on via Taro's defaults) is unaffected. This key is merged over
     * Taro's defaults by `recursiveMerge` in BaseConfig.setMinimizer.
     * NOTE: this lives in baseConfig (not prod.ts) on purpose — the config
     * function branches on `process.env.NODE_ENV`, but Taro forces
     * production mode for `taro build`, so a build with NODE_ENV=development
     * still minifies with the dev branch merged and would miss a prod-only
     * override (observed 2026-11-21: same `#"e"` SyntaxError in that combo).
     */
    terser: {
      config: {
        output: {
          quote_keys: false
        }
      }
    },
    cache: {
      enable: false // Webpack 持久化缓存配置，建议开启。默认配置请参考：https://docs.taro.zone/docs/config-detail#cache
    },
    mini: {
      postcss: {
        pxtransform: {
          enable: true,
          config: {

          }
        },
        cssModules: {
          enable: false, // 默认为 false，如需使用 css modules 功能，则设为 true
          config: {
            namingPattern: 'module', // 转换模式，取值为 global/module
            generateScopedName: '[name]__[local]___[hash:base64:5]'
          }
        }
      },
      webpackChain(chain) {
        chain.resolve.plugin('tsconfig-paths').use(TsconfigPathsPlugin)
      }
    },
    h5: {
      publicPath: '/',
      staticDirectory: 'static',
      output: {
        filename: 'js/[name].[hash:8].js',
        chunkFilename: 'js/[name].[chunkhash:8].js'
      },
      miniCssExtractPluginOption: {
        ignoreOrder: true,
        filename: 'css/[name].[hash].css',
        chunkFilename: 'css/[name].[chunkhash].css'
      },
      postcss: {
        autoprefixer: {
          enable: true,
          config: {}
        },
        cssModules: {
          enable: false, // 默认为 false，如需使用 css modules 功能，则设为 true
          config: {
            namingPattern: 'module', // 转换模式，取值为 global/module
            generateScopedName: '[name]__[local]___[hash:base64:5]'
          }
        }
      },
      webpackChain(chain) {
        chain.resolve.plugin('tsconfig-paths').use(TsconfigPathsPlugin)
      }
    },
  }


  if (process.env.NODE_ENV === 'development') {
    // 本地开发构建配置（不混淆压缩）
    return merge({}, baseConfig, devConfig)
  }
  // 生产构建配置（默认开启压缩混淆等）
  return merge({}, baseConfig, prodConfig)
})
