#!/usr/bin/env node
/**
 * Kiểm tra kích thước main package Mini Program < 2 MB (design doc §8.8).
 * GĐ1 chưa có subpackage nên toàn bộ dist/ (output của `build:weapp`) là
 * main package. Chạy sau `npm run build:weapp`.
 */
import { readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const dist = join(fileURLToPath(new URL('.', import.meta.url)), '..', 'dist')
const LIMIT_BYTES = 2 * 1024 * 1024

function sizeOf(dir) {
  let total = 0
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    const st = statSync(p)
    total += st.isDirectory() ? sizeOf(p) : st.size
  }
  return total
}

let total
try {
  total = sizeOf(dist)
} catch {
  console.error(`check-bundle-size FAILED — không đọc được ${dist} (chạy npm run build:weapp trước).`)
  process.exit(1)
}

const mb = (total / (1024 * 1024)).toFixed(2)
console.log(`main package: ${total} bytes (${mb} MB) — giới hạn 2.00 MB`)
if (total >= LIMIT_BYTES) {
  console.error('check-bundle-size FAILED — main package vượt 2 MB.')
  process.exit(1)
}
console.log('check-bundle-size OK')
