#!/usr/bin/env node
/**
 * Kiểm tra platform twins (design doc §8.8): mọi file `*.weapp.*` đều phải
 * có twin `*.h5.*` và ngược lại. Thiếu sibling platform là lỗi build theo
 * quy ước — kiểm tra ở CI bằng script này.
 *
 * Phạm vi: src/ui/primitives/**, src/services/**, src/providers.*,
 * src/components/** (mọi nơi dùng cặp platform file).
 */
import { readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(fileURLToPath(new URL('.', import.meta.url)), '..', 'src')
const SCOPES = ['ui/primitives', 'services', 'components']

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) walk(p, out)
    else if (/\.(weapp|h5)\.(ts|tsx)$/.test(name)) out.push(p)
  }
  return out
}

const missing = []
for (const scope of SCOPES) {
  const dir = join(root, scope)
  let files = []
  try {
    files = walk(dir)
  } catch {
    continue
  }
  for (const f of files) {
    const twin = f.replace(/\.(weapp|h5)\.(ts|tsx)$/, (_, platform, ext) =>
      platform === 'weapp' ? `.h5.${ext}` : `.weapp.${ext}`,
    )
    try {
      statSync(twin)
    } catch {
      missing.push(`${relative(join(root, '..'), f)} thiếu twin ${relative(join(root, '..'), twin)}`)
    }
  }
}
// src/providers.* là cặp file ở gốc src (không nằm trong scope trên).
for (const platform of ['weapp', 'h5']) {
  const twin = platform === 'weapp' ? 'h5' : 'weapp'
  for (const ext of ['ts', 'tsx']) {
    const f = join(root, `providers.${platform}.${ext}`)
    try {
      statSync(f)
      statSync(join(root, `providers.${twin}.${ext}`))
    } catch {
      // Chỉ báo khi một phía tồn tại mà phía kia không.
      let oneExists = false
      try {
        statSync(f)
        oneExists = true
      } catch {
        // phía này không tồn tại
      }
      if (oneExists) missing.push(`src/providers.${platform}.${ext} thiếu twin src/providers.${twin}.${ext}`)
    }
  }
}

if (missing.length > 0) {
  console.error('check-platform-twins FAILED:')
  for (const m of missing) console.error(`  - ${m}`)
  process.exit(1)
}
console.log('check-platform-twins OK')
