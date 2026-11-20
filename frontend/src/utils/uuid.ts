/**
 * UUID v4 — design doc §8.4: `crypto.randomUUID()` không được giả định là
 * tồn tại trong mọi runtime JS của Mini Program, nên fallback về
 * `crypto.getRandomValues`, cuối cùng là Math.random + Date.now.
 */
export function uuidv4(): string {
  const g = globalThis as unknown as {
    crypto?: { randomUUID?: () => string; getRandomValues?: (a: Uint8Array) => Uint8Array }
  }
  if (g.crypto?.randomUUID) return g.crypto.randomUUID()
  const bytes = new Uint8Array(16)
  if (g.crypto?.getRandomValues) {
    g.crypto.getRandomValues(bytes)
  } else {
    let seed = Date.now()
    for (let i = 0; i < 16; i++) {
      seed = (seed * 9301 + 49297) % 233280
      bytes[i] = Math.floor((seed / 233280) * 256)
    }
  }
  // RFC 4122 §4.4: version 4 + variant 10xx.
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}
