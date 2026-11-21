# IMSF Frontend (Taro React)

Frontend Giai đoạn 1: scaffold Taro 4.3.3 chính thức, theme từ IMSF Tokens,
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

## Adapter primitives (§8.2 — Step 3)

13 primitives ở `src/ui/primitives/<Name>/`, mỗi cái: `<Name>.types.ts`
(interface dùng chung) + `<Name>.weapp.tsx` (NutUI) + `<Name>.h5.tsx` (MUI)
+ `<Name>.ts` (fallback chỉ để tsc resolve — webpack MultiPlatformPlugin
luôn ưu tiên file `.weapp`/`.h5` khi tồn tại) + `index.ts`. Twin tests ở
`src/ui/primitives/primitives.test.tsx` (16 tests: render + tương tác giống
nhau ở cả 2 platform).

- **Toast:** `showToast(message, kind)` imperative + `ToastHost` mount 1 lần
  ở app shell. Weapp: `NutToast.show('imsf-toast', …)` qua custom event.
- **Dialog:** component khai báo + `confirmDialog(opts): Promise<boolean>`
  imperative qua `dialogStore.ts` dùng chung + `DialogHost`.
- **Uploader:** shell hiển thị thuần (preview + nút thêm) — transport thuộc
  `services/upload.ts` (§8.5), không dùng NutUI Uploader (transport tích hợp
  của nó xung đột với quyền sở hữu đó; NutUI Uploader đã chứng minh build ở
  Gate 0).
- **TabBar:** icon truyền bằng key (`home`/`fridge`/`recipes`/`mine`), mỗi
  platform map sang icon set native. Lệch nhỏ §4.1: `@nutui/icons-react-taro`
  3.0.2 không có icon tủ lạnh/sách/mũ đầu bếp — weapp dùng Store (冰箱) và
  List (菜谱); H5 dùng Kitchen + MenuBook đúng spec.
- **Cạm bẫy NutUI (đã kiểm chứng trên code đã cài):**
  - Truyền prop `undefined` tường minh sẽ GHI ĐÈ default của NutUI (nó gộp
    bằng spread): `InputNumber` `max={undefined}` → `Number(max)` = NaN.
    Chỉ spread prop khi có giá trị.
  - `Skeleton` `visible=true` nghĩa là HIỆN NỘI DUNG (ẩn skeleton) — ngược
    trực giác; primitive luôn truyền `visible={false}`.
  - `Picker` `options` là MẢNG CÁC CỘT (`PickerOptions[]`): 1 cột → `[options]`.
  - `InputNumber` nút + là async (await `beforeChange`) — test phải `waitFor`.
  - MUI v9: system props (`display`, `position`, `width`, `bgcolor`…)
    KHÔNG còn là prop trực tiếp của `Box` — phải cho vào `sx`; `TextField`
    `inputProps` → `slotProps.htmlInput`; `Switch` `inputProps` →
    `slotProps.input`; `ListItemText` không còn `primaryTypographyProps`;
    `Switch` input có `role="switch"`.
- **Test setup (`vitest.config.ts`, `src/test/`):** Vitest externalize NutUI
  ESM native → import `@tarojs/*` bên trong NutUI bypass `vi.mock` và load
  runtime thật (nổ `ENABLE_INNER_HTML` — global chỉ có khi build webpack).
  Khắc phục: `server.deps.inline` cho NutUI/Taro + alias `@tarojs/taro` /
  `@tarojs/components` về stub (`taroStub.ts`, `taroComponentsStub.tsx`) +
  `define` 7 global `ENABLE_* = false` + alias NutUI root về entry ESM
  (tránh UMD bundle chạy lottie canvas detection lúc load) + mock
  `lottie-web` / `lottie-react` trong setup (không test nào render Lottie).
  `@testing-library/dom@10.4.2` cài riêng (peer của react 16.3.3, bị
  `--legacy-peer-deps` bỏ qua). `cleanup()` tay trong `afterEach` (Vitest
  không có `globals: true` nên RTL không tự cleanup).

## Hai mục mở (design doc §10.2)

- **D-F2 (reprocess endpoint):** backend KHÔNG có endpoint reprocess — cả hai
  nút 重新识别 (Màn 02 + 03) đều ẨN. Chỉ hiện 重新上传.
- **D-F3 (confirm payload dòng thêm):** dòng client thêm gửi `line_id: null`.
  Backend hiện tại yêu cầu UUID (422 nếu khác) — đang chờ backend xác nhận.

## Step 4 — App shell + Screen 01

- **Providers:** `src/providers.weapp.tsx` (NutUI ConfigProvider zh-CN) /
  `src/providers.h5.tsx` (MUI ThemeProvider + CssBaseline; `Taro.hideTabBar()`
  trong `useEffect` vì H5 bỏ qua tabBar.custom). `src/app.tsx` thay `app.ts`
  (Taro ưu tiên `.ts` trước `.tsx` khi resolve — hai file không được cùng tồn
  tại). `app.tsx` đăng ký network listener (mất mạng → ui store `isOnline`
  false + OfflineBanner; có mạng lại → `invalidateQueries()`) và
  session-expired handler → `goLogin()`. `app.config.ts`: pages upload đầu
  tiên (launch), `navigationStyle: 'custom'`, tabBar custom với slot giữa
  trỏ lại upload (FAB placeholder — custom bar chặn tap).
- **Tab bar:** `src/components/AppTabBar/` là component duy nhất, mount ở
  `src/custom-tab-bar/index.tsx` (weapp) và `TabBarHost.h5.tsx` (H5);
  `TabBarHost.weapp.tsx` render null. `useTabBarSelected` đồng bộ tab vào ui
  store + `getTabBar().setData({selected})` (weapp). Divider nằm TRÊN nav,
  là sibling của nav — KHÔNG trong hàng nav (§4.1, lỗi Figma đã biết).
- **Icon primitive mới** (`src/ui/primitives/Icon/`, §8.2 "thêm khi cần"):
  13 key (camera, chevron-left/right, check, clock, close, error, image,
  plus, refresh, search, warning, info) — NutUI icons weapp, MUI icons H5,
  twin test đủ 13 key. **ListRow thêm slot `left?: ReactNode`** — ReceiptRow
  dùng vòng tròn glyph 40px; khi có `left`, subtitle render trong cột title
  (căn dưới title, không nằm dưới vòng tròn).
- **Business components:** StatusChip (4 trạng thái, màu từ tokens.status),
  PageHeader (56px, title 20 semibold + subtitle 14, back chevron 44px),
  OfflineBanner (amber, khi `isOnline` false), EmptyState (pattern §7.2:
  icon dashed 64px + title + body + một action), ReceiptRow (vòng glyph +
  ngày tương đối + số tiền — chỉ hiển thị khi completed/needs_review, còn lại
  「—」; tên cửa hàng thiếu → 「未知商家」), ReceiptList (skeleton 3 dòng,
  panel lỗi + [重试], empty state do cha truyền, `limit`).
- **Màn 01 (§5.1):** capture card 180px dashed 1.5px primary 60%, bg
  primaryContainer 40% (qua `withAlpha` trong `utils/format.ts`, không thêm
  token mới); tap card = camera; preview + ✕ gỡ + progress xác định +
  正在上传…; lỗi inline dưới card (⚠ + text + 重新选择/重新上传), không toast;
  202 → navigateTo `/receipts/{id}` + toast「小票已上传，正在识别」; 403 →
  inline「您没有权限上传到该家庭账本」; offline chặn pick với「无网络连接，
  请联网后上传」; recent list 3 dòng + 查看全部 ›; pull-to-refresh
  (enablePullDownRefresh, xác nhận「已更新」); skeleton 3 dòng chỉ khi load
  lần đầu >300ms; empty state + 立即拍照; chưa login → card「请先登录」+
  去登录. FAB ở tab khác → mở camera khi về upload (ui store
  `openCameraOnShow`, trang upload tự clear).
- **Trang khác:** fridge/recipes placeholder honest (§4.1, §7.2); mine
  (household name/role/currency/timezone/locale chỉ đọc + switcher nếu >1 +
  logout — KHÔNG có số thành viên vì API không trả); login (wx.login →
  code → POST /auth/wechat; H5 login thất bại → 「请在微信中打开小程序登录」);
  receipts (filter chip 全部/处理中/需核对/已完成/识别失败 — backend chỉ lọc
  đúng một status nên chip「处理中」gộp pending + processing, lọc ở client).
- **Copy KHÔNG trong doc (ghi vào báo cáo cuối):** recipes placeholder body
  「第一批食材入库后，这里会显示菜谱推荐。」(cấu trúc song song với fridge);
  login「请先登录」/「登录后即可查看最近小票」/「微信登录」/「请使用微信登录以继续」.

## Step 5 — Screens 02 + 03 (một route /receipts/{id}, đổi nội dung theo status)

- **Một page instance, không redirectTo khi needs_review:** Màn 02 và Màn 03
  là cùng một component đổi nội dung theo `status` — back không bao giờ về
  spinner cũ vì stack chỉ có một trang receipt (đúng ý đồ doc §5.2; không
  cần redirectTo). Back dùng `goBackOrUpload()` (deep link cold start không
  có stack → về Upload).
- **Màn 02 (§5.2):** checklist 3 bước determinate (KHÔNG % giả) — ánh xạ từ
  status: pending → bước 1 active; processing → bước 1 xong, bước 2 active,
  bước 3 chờ (API không có sub-step nên không thể biết chính xác hơn);
  dot active pulse (CSS keyframes `index.scss`); thanh indeterminate phụ;
  「已用时 m:ss」tính từ `created_at` (tuổi thật của job), tick mỗi giây;
  「通常需要 30 秒到 2 分钟，请稍等。」; secondary duy nhất「先去看看别的，
  好了通知我」. Soft timeout 180s (job age): copy đổi + nút rời thành primary.
  Hard timeout 300s (job age): dừng polling + panel「处理超时」+ 稍后查看 /
  重新上传 — KHÔNG đánh failed phía client. Failure: `error_message` nguyên
  văn + 重新上传 (về Màn 01, camera mở, key mới) + 查看小票图片 (previewImage).
  Completed tại chỗ: 「识别完成」+「已入库 N 件食材」+ 查看冰箱 / 返回首页.
- **Màn 03 (§5.3):** header 核对小票 + subtitle; image card (max-height
  240px, skeleton cùng chiều cao khi load, tap → previewImage, caption
  「点按图片可放大查看」); mismatch card (warningContainer, border warning
  40%, icon ⚠ + text) với 3 số + % (1dp) — live theo draft; nếu không lệch
  mà có dòng chưa map thì card「有 N 行商品未能识别，请确认或修改。」.
  Line editor: 数量/单位 (picker 8 giá trị)/单价 ¥/小计 tự cập nhật, label
  nhìn thấy trên mỗi field; chip canonical_name hoặc 未匹配 (tap → input gõ
  tên chuẩn — xem lưu ý dưới); dòng giảm giá/phí (giá âm hoặc tên khớp
  优惠/折扣/运费/服务费): border trái secondary 3px + tag 优惠/费用, toggle
  ẩn; switch 记入冰箱库存 + hint; 删除此行 + thanh undo 5s (「已删除 1 行」
  + 撤销, render trong action bar cố định — không dùng Toast primitive vì
  nó không có action). ＋ 添加一行 (dòng trống, raw_name có label 商品名称).
  Live summary sticky trên action bar, chuyển xanh khi trong 2%.
  Confirm KHÔNG bao giờ disable; lỗi inline dưới field + cuộn tới lỗi đầu
  (pageScrollTo) + toast「有 N 项需要修改，请检查标红处」. 422 map từ body
  FastAPI (loc body/lines/i/field) về slot inline — ApiError giờ mang `data`.
  409 → refetch + toast「小票状态已更新，请查看最新结果」. Confirm vẫn lệch
  → ở lại màn, card cập nhật, toast「仍有差额，请继续核对」, KHÔNG reset form
  (draft chỉ init một lần mỗi receipt, bỏ khi unmount).
- **Lưu ý D-F3 / canonical name:** ConfirmLine backend chỉ có 5 field
  (`line_id`, `quantity`, `unit`, `price`, `is_stock_item`) — KHÔNG có
  `canonical_name` và không có endpoint search ingredient — nên input tên
  chuẩn cho dòng 未匹配 là display-only (chip đổi theo text gõ) cho tới khi
  backend thêm field. Payload confirm gửi `price` = tiểu kế (qty × đơn giá).
- **Copy KHÔNG trong doc (ghi vào báo cáo cuối):** header completed
  「小票详情」; message lỗi giá 「请输入金额」/「金额不能为负数」/
  「优惠金额不能为正数」và unit 「请选择单位」 (doc chỉ cho 数量/2dp/raw_name).

## Step 6 — Build + CI + 3 lỗi build H5 (đều là lỗi thật, đã fix + test)

CI: `.github/workflows/frontend.yml` (job riêng, paths `frontend/**`, không
đụng job Python). Lệch khỏi doc §8.8 (ghi trong header workflow): paths
`frontend/**` (không phải `imsf-frontend/**`); build H5 trước, weapp sau
(cả hai cùng ghi `dist/`, weapp phải là artifact cuối cho DevTools); thêm
`theme:check`; `npm ci --legacy-peer-deps` (vite 8 vs peerOptional vite ^4
của `@tarojs/plugin-framework-react` — `npm ci` thường fail ERESOLVE).

Ba lỗi chỉ lộ khi chạy H5 build thật trên trình duyệt (build exit 0 nhưng
bundle không chạy được — `build:weapp`/`build:h5` xanh không đủ, phải parse
bundle bằng acorn + render thật):

1. **Terser `quote_keys` → `#"e"` (SyntaxError).** Taro 4.3.3 H5 mặc định
   `output.quote_keys: true`; Terser 5.51.4 quote cả private field, sinh
   `#"e";` (class `Mutation` của @tanstack/query-core) — V8/Chromium đều
   reject (acorn: `app.js 2:80049`). Weapp KHÔNG bị (mini defaults không có
   `quote_keys`; 14/14 file weapp parse OK). Fix: `terser.config.output.
   quote_keys: false` trong `config/index.ts` (baseConfig — KHÔNG để ở
   `prod.ts`: config branch theo `NODE_ENV` nhưng Taro ép production mode
   cho `taro build`, nên build với `NODE_ENV=development` vẫn minify mà
   không merge prodConfig — đã tái hiện lỗi này). Đã tái hiện tối thiểu
   bằng Terser trực tiếp trên class `Mutation` trước khi fix.
2. **MUI error #6 — `responsiveFontSizes` ném lỗi ở module load.**
   `muiTheme.ts` truyền `lineHeight: "36px"` (chuỗi có đơn vị); MUI yêu cầu
   lineHeight không đơn vị khi dùng grid alignment. Fix: `unitlessLineHeight
   (size, lineHeight) = round(lh/size, 4dp)` cho cả 11 variant (h1 36/28…),
   giữ nguyên token px ở cỡ chữ gốc; `responsiveFontSizes` (doc §3.3 bắt
   buộc) vẫn được giữ. Regression test `src/ui/muiTheme.test.ts` (3 test —
   import theme là chạy `responsiveFontSizes`, fail trước fix, pass sau).
   Lưu ý doc §3.3: "(h1 → 32px ở ≥1024px)" KHÔNG thể đúng với token h1
   28px — `responsiveFontSizes` chỉ scale-down từ cỡ theme, không vượt quá
   28px (test assert h1 = 1.75rem ở `@media (min-width:1440px)`); muốn 32px
   thì token h1 phải là 32 — chờ Lam quyết, không tự đổi token.
3. **`ReferenceError: process is not defined` (H5).** `src/config/env.ts`
   đọc `process.env.TARO_APP_API_BASE_URL`; khi biến không có trong `.env*`,
   Taro không define nó cho DefinePlugin nên biểu thức còn nguyên trong
   bundle, browser crash (browser không có `process`). Fix: default
   `env: { TARO_APP_API_BASE_URL: '""' }` trong `config/index.ts` —
   `patchEnv` gộp `Object.assign({}, config.env, dotenv)` nên giá trị thật
   từ `.env*`/`.env*.local`/CI secret GHI ĐÈ default, không bao giờ mất
   (đã verify: build với `.env.production.local` chứa
   `http://52.13.176.85:8002` → bundle chứa đúng URL đó; file test đã xóa).
   Sau fix: bundle không còn `process.env.` nào; `API_BASE_URL = ""`.

- **Render proof H5 (Screen 01):** serve `dist/h5` + Chromium headless
  375×812 — DOM 29KB, 0 console error, screenshot thấy đủ header「拍小票，
  自动记账入库」, capture card dashed, 2 nút 拍照 / 从相册选择, 最近小票 +
  login gate「请先登录」/「登录后即可查看最近小票」+ 去登录, tab bar 4 mục +
  FAB camera. (Logged-out nên empty state「还没有小票」không hiện — đúng
  theo login gate Step 4.)
- **Nit chưa fix (cosmetic, H5 375px):** label「从相册选择」wrap 2 dòng trong
  nút nửa chiều rộng. Button primitive không có style/sx passthrough nên
  fix cần thêm prop cho adapter (cả 2 platform + twin test) — để follow-up,
  không sửa lén trong Step 6.
