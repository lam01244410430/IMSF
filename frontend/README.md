# IMSF-v2 Frontend (Taro React)

Frontend Giai đoạn 1: scaffold Taro 4.3.3 chính thức, theme từ IMSF-v2 Tokens,
app shell (bottom nav + camera FAB), 3 màn lõi GĐ1 (Upload, Processing,
Needs Review), API client đầy đủ cho GĐ1. Thiết kế: xem
`~/workspace/user/files/IMSF-v2-frontend-design.md` (§§1–11) — tài liệu này là
nguồn chân lý duy nhất; mọi lệch khỏi nó phải ghi số section trong báo cáo.

## Stack đã pin (§8.1)

- Taro CLI **4.3.3**, React **18**, TypeScript (strict), sass, compiler **webpack5**
- MUI **@mui/material@9.5.0** + Emotion 11.14.x — chỉ H5 (cần DOM thật)
- NutUI React **@nutui/nutui-react-taro@3.0.20** (pin chính xác, không `^`) —
  chỉ Mini Program. KHÔNG dùng v4.0.0 (mới <24h lúc thiết kế, zero proof).
- Zustand v5 (client state) + TanStack Query v5 (server state)
- Vitest 5 + jsdom (test). Node 22 LTS.

## Lệnh

| Lệnh | Làm gì |
|---|---|
| `npm run theme:build` | Sinh `src/ui/tokens.css` + `src/ui/nutui.css` từ `tokens.ts` |
| `npm run theme:check` | Fail nếu CSS sinh ra khác file đã commit (CI) |
| `npm run typecheck` | `tsc --noEmit` |
| `npm run lint` | ESLint (gồm no-restricted-imports + quy tắc TARO_ENV) |
| `npm run test` | Vitest |
| `npm run build:weapp` | `taro build --type weapp` → `dist/` |
| `npm run build:h5` | `taro build --type h5` → `dist/` (cùng outputRoot — xem dưới) |
| `npm run check:twins` | Mọi `*.weapp.*` đều có twin `*.h5.*` |
| `npm run check:bundle` | Main package weapp < 2 MB (chạy sau build:weapp) |

**Lưu ý output:** Taro 4.3.3 webpack5 không hỗ trợ outputRoot riêng theo
target — cả hai build đều ghi vào `dist/`, build sau ghi đè build trước.
CI chạy `build:h5` trước rồi `build:weapp` sau để `dist/` cuối cùng là output
weapp (mở bằng WeChat DevTools). Lệch với design doc §8.8 (ghi `dist/h5/`).

## Quy tắc bắt buộc (§8.2)

1. **Token là chân lý duy nhất:** một giá trị màu/spacing/radius chỉ tồn tại
   ở `src/ui/tokens.ts`. Không hardcode hex trong component (ESLint cấm hex
   ngoài `src/ui/`; `tokens.css`/`nutui.css` sinh ra, không chỉnh tay).
2. **Component mới render primitive native/DOM** (button, input, dialog, list
   row) → `src/ui/primitives/<Name>/` với `.weapp.tsx` + `.h5.tsx` +
   `.types.ts` chia sẻ. Không bao giờ import `@mui/*` / `@nutui/*` ở nơi
   khác (ESLint `no-restricted-imports`; ngoại lệ duy nhất: theme wiring
   `src/ui/muiTheme.ts`, `src/ui/nutuiTheme.ts`, `src/providers.*`).
3. **Component compose primitive + business logic** → `src/components/<Name>/`,
   chỉ import từ `ui/primitives`.
4. **API platform** (camera, storage, navigation) → `src/services/<name>.weapp.ts`
   / `<name>.h5.ts` với một interface chia sẻ, cùng pattern với primitives.
5. **Logic thuần** (formatting, validation, mapping) → `src/utils/`, không
   platform, unit-test bằng Vitest.
6. **Không `if (TARO_ENV === …)` trong page** — ESLint `no-restricted-syntax`
   trên `process.env.TARO_ENV` ngoài `src/ui/**` và `src/services/**`.
7. **Không MDUI** trong app này. Không react-router (chỉ router Taro, xem
   `src/config/routes.ts`).

## API client (§8.4/§8.5)

- Transport `Taro.request` / `Taro.uploadFile` (không axios/fetch).
- Base URL qua `TARO_APP_API_BASE_URL` (`.env*`), không hardcode IP/host.
- JWT 15 phút + refresh single-flight; refresh chủ động khi còn < 60s.
- Idempotency-Key: UUID mỗi lần pick, dùng lại qua mọi retry của cùng pick.
- Polling receipt: 3s trong 60s đầu → 5s; soft notice 180s; hard stop 300s.
- `price` trong receipt_line / payload confirm là **tiểu kế của dòng**
  (backend đối soát bằng SUM(price)) — UI sửa đơn giá thì gửi
  `price = round2(quantity × unitPrice)`.

## Hai mục mở (design doc §10.2)

- **D-F2 (reprocess endpoint):** backend KHÔNG có endpoint reprocess — cả hai
  nút 重新识别 (Màn 02 + 03) đều ẨN. Chỉ hiện 重新上传.
- **D-F3 (confirm payload dòng thêm):** dòng client thêm gửi `line_id: null`.
  Backend hiện tại yêu cầu UUID (422 nếu khác) — đang chờ backend xác nhận.
