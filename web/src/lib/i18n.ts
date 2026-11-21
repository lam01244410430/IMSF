/**
 * Tiny i18n for the IMSF website — no library, just a typed dictionary
 * + React context (reform plan §4.1: zh-CN default, vi + en supported).
 *
 * This file holds the dictionaries and the context object only (no
 * JSX, so it stays a `.ts` file). The `LanguageProvider` component
 * lives in `./LanguageProvider.tsx` — keeping components and plain
 * values in separate files keeps oxlint's only-export-components
 * rule quiet (the foundation lints with 0 warnings).
 *
 * - Default language zh-CN (China-first); the choice is stored in
 *   localStorage (`imsf.lang`) and switching re-renders the same route.
 * - Every key exists in all three languages: `Dict` is `typeof zh`, so
 *   a missing vi/en key is a compile error, not a runtime gap.
 * - All copy is hand-written. The zh-CN + vi strings come from the
 *   reform plan (§4.3–§4.8, §7.8); the en strings are careful
 *   translations written for this module — no placeholder English.
 */
import { createContext, useContext } from 'react'

export type Language = 'zh-CN' | 'vi' | 'en'

export const LANGUAGE_STORAGE_KEY = 'imsf.lang'

export const LANGUAGES: { code: Language; label: string }[] = [
  { code: 'zh-CN', label: '中文' },
  { code: 'vi', label: 'Tiếng Việt' },
  { code: 'en', label: 'English' },
]

function isLanguage(value: string): value is Language {
  return value === 'zh-CN' || value === 'vi' || value === 'en'
}

export function getStoredLanguage(): Language {
  try {
    const stored = window.localStorage.getItem(LANGUAGE_STORAGE_KEY)
    if (stored && isLanguage(stored)) return stored
  } catch {
    // storage unavailable — fall through to the default.
  }
  return 'zh-CN'
}

const zh = {
  'skip.link': '跳到主要内容',
  'lang.label': '语言',
  'nav.features': '功能',
  'nav.how': '使用方法',
  'nav.recipes': '菜谱',
  'nav.faq': '常见问题',
  'header.login': '登录',
  'header.register': '注册',
  'header.enterApp': '进入应用',
  'header.menuOpen': '打开菜单',
  'header.menuClose': '关闭菜单',
  'header.menuLabel': '菜单',
  'hero.title': '拍一张小票，冰箱和账本都记好了。',
  'hero.subtitle':
    'IMSF 帮一家人管好冰箱、记好每一笔支出，快过期的食材还会推荐菜谱。',
  'hero.vp1': '拍照自动入库记账',
  'hero.vp2': '快过期，推荐菜谱',
  'hero.vp3': '一家人，共用一本账',
  'hero.ctaPrimary': '开始免费使用',
  'hero.ctaSecondary': '看看使用方法',
  'hero.mockTitle': '应用预览',
  'hero.mockText': '界面预览（示意）',
  'trust.t1': '为家庭而做',
  'trust.d1': '为一家人日常做饭、记账、管理冰箱而设计，不是为企业报表。',
  'trust.t2': '没有广告',
  'trust.d2': '界面里没有广告，也不会向你推销任何东西。',
  'trust.t3': '你的数据属于你',
  'trust.d3': '只有同一家庭的成员能看到你家的数据。',
  'features.f1t': '智能识别小票',
  'features.f1d':
    '拍下小票，自动识别商品、价格和总价，核对无误后一键入库记账。支持中文和越南文小票。',
  'features.f1l': '了解更多',
  'features.f2t': '智能冰箱',
  'features.f2d':
    '每件食材都有保质期提醒。快过期时，IMSF 会问你一句，用一键回答：吃完了，还是再放三天。',
  'features.f2l': '了解更多',
  'features.f3t': '家庭账本',
  'features.f3d':
    '手动记一笔，或者从小票自动记账。按月查看支出，按分类汇总，支持 14 种货币，每种货币单独汇总，不混算、不换算。',
  'features.f3l': '了解更多',
  'features.f4t': '社区菜谱',
  'features.f4d':
    '看看别人用快过期的食材做了什么菜。喜欢的菜谱可以收藏，照着做，还能一键生成购物清单。',
  'features.f4l': '去看看菜谱',
  'features.f5t': '设备保养',
  'features.f5d':
    '记下每台设备的购买日期和保养周期，到期前提醒你，保养记录随时可查。',
  'features.f5l': '了解更多',
  'features.mockLabel': '界面预览（示意）',
  'how.title': '使用方法',
  'how.s1t': '拍小票',
  'how.s1d': '买菜回来，拍一张小票。',
  'how.s2t': '自动入库记账',
  'how.s2d': 'IMSF 识别商品并核对总价，确认后食材进冰箱、支出进账本。',
  'how.s3t': '快过期，做道菜',
  'how.s3d': '食材快过期时，看看菜谱推荐，做一道菜，不浪费。',
  'how.cta': '开始免费使用',
  'video.text': '演示视频即将上线',
  'reviews.title': '大家怎么说',
  'reviews.empty': '虚位以待 — 第一批家庭的使用反馈会出现在这里。',
  'faq.title': '常见问题',
  'faq.q1': 'IMSF 免费吗？',
  'faq.a1': '家庭使用免费，没有付费套餐，也没有广告。以后如果有付费功能，会提前告诉你。',
  'faq.q2': '支持哪些语言？',
  'faq.a2':
    '界面支持中文、越南文和英文，右上角可以随时切换。中文小票和越南文小票都可以识别。',
  'faq.q3': '怎么登录？用微信还是邮箱？',
  'faq.a3': '网页版用邮箱登录，微信小程序里用微信登录。',
  'faq.q4': '我的数据存在哪里？谁能看到？',
  'faq.a4':
    '你的数据保存在你家庭的账本里，只有同一家庭的成员能看到。换手机、换设备，登录同一账号就能看到。',
  'faq.q5': '在越南能用吗？',
  'faq.a5':
    '能用。支持越南文小票、越南盾（VND）和越南文界面，14 种货币里包括 VND、CNY、USD 等，每种货币单独汇总。',
  'cta.title': '现在就开始，和家人一起用 IMSF。',
  'cta.button': '开始免费使用',
  'footer.product': '产品',
  'footer.start': '开始使用',
  'footer.help': '帮助',
  'footer.legal': '法律',
  'footer.features': '功能',
  'footer.how': '使用方法',
  'footer.recipes': '菜谱',
  'footer.faq': '常见问题',
  'footer.register': '注册',
  'footer.login': '登录',
  'footer.enterApp': '进入应用',
  'footer.contact': '联系我们',
  'footer.privacy': '隐私政策',
  'footer.terms': '服务条款',
  'footer.tagline': 'IMSF — 为一家人管好冰箱和账本。',
  'legal.privacyTitle': '隐私政策',
  'legal.termsTitle': '服务条款',
  'legal.contactTitle': '联系我们',
  'legal.wip': '正在编写中',
  'legal.wipText': '本文档正在编写中，内容确定后会在此公布。',
  'legal.contactText': '联系方式即将公布。',
  'legal.back': '返回首页',
  'auth.loginTitle': '登录',
  'auth.registerTitle': '注册',
  'auth.email': '邮箱',
  'auth.password': '密码',
  'auth.confirmPassword': '确认密码',
  'auth.name': '姓名（可选）',
  'auth.loginSubmit': '登录',
  'auth.registerSubmit': '注册',
  'auth.loadingLogin': '登录中…',
  'auth.loadingRegister': '注册中…',
  'auth.noAccount': '还没有账号？去注册',
  'auth.hasAccount': '已有账号？去登录',
  'auth.goLogin': '去登录',
  'auth.note': '网页端仅支持邮箱登录；微信登录请在小程序中使用。',
  'auth.showPassword': '显示密码',
  'auth.hidePassword': '隐藏密码',
  'auth.lockedCountdown': '已锁定，{mm}:{ss} 后可重试',
  'err.invalidCredentials': '邮箱或密码错误',
  'err.emailTaken': '该邮箱已被注册，请直接登录',
  'err.tooFrequent': '请求过于频繁，请稍后再试',
  'err.locked': '密码错误次数过多，该账号已被暂时锁定，请15分钟后再试',
  'err.invalidEmail': '请输入有效的邮箱地址',
  'err.passwordShort': '密码至少8位',
  'err.passwordMismatch': '两次输入的密码不一致',
  'err.network': '网络错误，请检查网络后重试',
  'err.server': '服务暂时不可用，请稍后再试',
} as const

/**
 * `Dict` is a plain-string map over the zh-CN keys: a missing vi/en
 * key is still a compile error, but values are `string`, not the
 * zh-CN literal (translations are different strings, obviously).
 */
export type Dict = { [K in keyof typeof zh]: string }

const vi: Dict = {
  'skip.link': 'Đi tới nội dung chính',
  'lang.label': 'Ngôn ngữ',
  'nav.features': 'Tính năng',
  'nav.how': 'Cách hoạt động',
  'nav.recipes': 'Công thức',
  'nav.faq': 'Câu hỏi thường gặp',
  'header.login': 'Đăng nhập',
  'header.register': 'Đăng ký',
  'header.enterApp': 'Vào ứng dụng',
  'header.menuOpen': 'Mở menu',
  'header.menuClose': 'Đóng menu',
  'header.menuLabel': 'Menu',
  'hero.title': 'Chụp một tờ hoá đơn, tủ lạnh và sổ chi tiêu đều đã ghi xong.',
  'hero.subtitle':
    'IMSF giúp cả nhà quản tủ lạnh, ghi từng khoản chi, và gợi ý món ăn từ nguyên liệu sắp hết hạn.',
  'hero.vp1': 'Chụp là tự nhập kho + ghi sổ',
  'hero.vp2': 'Sắp hết hạn thì gợi ý món ăn',
  'hero.vp3': 'Cả nhà dùng chung một sổ',
  'hero.ctaPrimary': 'Bắt đầu dùng miễn phí',
  'hero.ctaSecondary': 'Xem cách hoạt động',
  'hero.mockTitle': 'Xem trước ứng dụng',
  'hero.mockText': 'Xem trước giao diện (minh hoạ)',
  'trust.t1': 'Làm ra cho gia đình',
  'trust.d1':
    'Thiết kế cho việc nấu ăn, ghi sổ và quản tủ lạnh hằng ngày của một gia đình — không phải cho báo cáo doanh nghiệp.',
  'trust.t2': 'Không quảng cáo',
  'trust.d2':
    'Trong giao diện không có quảng cáo, và chúng tôi cũng không chào bán gì với bạn.',
  'trust.t3': 'Dữ liệu của bạn là của bạn',
  'trust.d3': 'Chỉ thành viên cùng gia đình mới xem được dữ liệu nhà bạn.',
  'features.f1t': 'Nhận diện hoá đơn thông minh',
  'features.f1d':
    'Chụp hoá đơn, tự nhận diện món hàng, giá và tổng tiền; đối soát xong thì một chạm nhập kho + ghi sổ. Hỗ trợ hoá đơn tiếng Trung và tiếng Việt.',
  'features.f1l': 'Tìm hiểu thêm',
  'features.f2t': 'Tủ lạnh thông minh',
  'features.f2d':
    'Mỗi nguyên liệu đều có nhắc hết hạn. Sắp hết hạn, IMSF hỏi một câu, bạn trả lời một chạm: đã dùng hết, hay để thêm ba ngày.',
  'features.f2l': 'Tìm hiểu thêm',
  'features.f3t': 'Sổ chi tiêu gia đình',
  'features.f3d':
    'Ghi tay một khoản, hoặc tự ghi từ hoá đơn. Xem chi tiêu theo tháng, tổng hợp theo danh mục, hỗ trợ 14 loại tiền tệ, mỗi loại tổng riêng, không cộng trộn, không quy đổi.',
  'features.f3l': 'Tìm hiểu thêm',
  'features.f4t': 'Công thức cộng đồng',
  'features.f4d':
    'Xem người khác nấu món gì từ nguyên liệu sắp hết hạn. Công thức thích thì lưu lại, nấu theo, và một chạm tạo danh sách đi chợ.',
  'features.f4l': 'Xem công thức',
  'features.f5t': 'Bảo trì thiết bị',
  'features.f5d':
    'Ghi ngày mua và chu kỳ bảo trì của từng thiết bị, nhắc trước khi tới hạn, lịch sử bảo trì tra cứu bất cứ lúc nào.',
  'features.f5l': 'Tìm hiểu thêm',
  'features.mockLabel': 'Xem trước giao diện (minh hoạ)',
  'how.title': 'Cách hoạt động',
  'how.s1t': 'Chụp hoá đơn',
  'how.s1d': 'Đi chợ về, chụp một tờ hoá đơn.',
  'how.s2t': 'Tự nhập kho, tự ghi sổ',
  'how.s2d':
    'IMSF nhận diện món hàng và đối soát tổng tiền; xác nhận xong, nguyên liệu vào tủ lạnh, khoản chi vào sổ.',
  'how.s3t': 'Sắp hết hạn thì nấu một món',
  'how.s3d':
    'Nguyên liệu sắp hết hạn, xem gợi ý công thức, nấu một món, không lãng phí.',
  'how.cta': 'Bắt đầu dùng miễn phí',
  'video.text': 'Video demo sắp ra mắt',
  'reviews.title': 'Mọi người nói gì',
  'reviews.empty':
    'Chờ phản hồi thật — nhận xét của những gia đình đầu tiên sẽ hiện ở đây.',
  'faq.title': 'Câu hỏi thường gặp',
  'faq.q1': 'IMSF có miễn phí không?',
  'faq.a1':
    'Miễn phí cho gia đình sử dụng, không có gói trả phí, không quảng cáo. Sau này nếu có tính năng trả phí, chúng tôi sẽ báo trước.',
  'faq.q2': 'Hỗ trợ ngôn ngữ nào?',
  'faq.a2':
    'Giao diện hỗ trợ tiếng Trung, tiếng Việt và tiếng Anh, đổi bất cứ lúc nào ở góc phải. Hoá đơn tiếng Trung và tiếng Việt đều nhận diện được.',
  'faq.q3': 'Đăng nhập thế nào? Dùng WeChat hay email?',
  'faq.a3':
    'Bản web đăng nhập bằng email, trong Mini Program WeChat thì đăng nhập bằng WeChat.',
  'faq.q4': 'Dữ liệu của tôi lưu ở đâu? Ai xem được?',
  'faq.a4':
    'Dữ liệu lưu trong sổ của gia đình bạn, chỉ thành viên cùng gia đình mới xem được. Đổi điện thoại hay thiết bị, đăng nhập cùng tài khoản là xem được.',
  'faq.q5': 'Dùng ở Việt Nam được không?',
  'faq.a5':
    'Dùng được. Hỗ trợ hoá đơn tiếng Việt, đồng VND và giao diện tiếng Việt; trong 14 loại tiền tệ có VND, CNY, USD…, mỗi loại tổng riêng.',
  'cta.title': 'Bắt đầu ngay hôm nay — cả nhà cùng dùng IMSF.',
  'cta.button': 'Bắt đầu dùng miễn phí',
  'footer.product': 'Sản phẩm',
  'footer.start': 'Bắt đầu',
  'footer.help': 'Trợ giúp',
  'footer.legal': 'Pháp lý',
  'footer.features': 'Tính năng',
  'footer.how': 'Cách hoạt động',
  'footer.recipes': 'Công thức',
  'footer.faq': 'Câu hỏi thường gặp',
  'footer.register': 'Đăng ký',
  'footer.login': 'Đăng nhập',
  'footer.enterApp': 'Vào ứng dụng',
  'footer.contact': 'Liên hệ với chúng tôi',
  'footer.privacy': 'Chính sách bảo mật',
  'footer.terms': 'Điều khoản dịch vụ',
  'footer.tagline': 'IMSF — giúp cả nhà quản tủ lạnh và sổ chi tiêu.',
  'legal.privacyTitle': 'Chính sách bảo mật',
  'legal.termsTitle': 'Điều khoản dịch vụ',
  'legal.contactTitle': 'Liên hệ với chúng tôi',
  'legal.wip': 'Đang được soạn thảo',
  'legal.wipText':
    'Trang này đang được soạn thảo; nội dung sẽ được công bố tại đây khi hoàn thiện.',
  'legal.contactText': 'Thông tin liên hệ sẽ sớm được công bố.',
  'legal.back': 'Về trang chủ',
  'auth.loginTitle': 'Đăng nhập',
  'auth.registerTitle': 'Đăng ký',
  'auth.email': 'Email',
  'auth.password': 'Mật khẩu',
  'auth.confirmPassword': 'Nhập lại mật khẩu',
  'auth.name': 'Tên (tùy chọn)',
  'auth.loginSubmit': 'Đăng nhập',
  'auth.registerSubmit': 'Đăng ký',
  'auth.loadingLogin': 'Đang đăng nhập…',
  'auth.loadingRegister': 'Đang đăng ký…',
  'auth.noAccount': 'Chưa có tài khoản? Đăng ký',
  'auth.hasAccount': 'Đã có tài khoản? Đăng nhập',
  'auth.goLogin': 'Đăng nhập ngay',
  'auth.note':
    'Bản web chỉ hỗ trợ đăng nhập bằng email; đăng nhập bằng WeChat dùng trong Mini Program.',
  'auth.showPassword': 'Hiện mật khẩu',
  'auth.hidePassword': 'Ẩn mật khẩu',
  'auth.lockedCountdown': 'Đã khóa, thử lại sau {mm}:{ss}',
  'err.invalidCredentials': 'Email hoặc mật khẩu không đúng',
  'err.emailTaken': 'Email này đã được đăng ký, vui lòng đăng nhập',
  'err.tooFrequent': 'Yêu cầu quá thường xuyên, vui lòng thử lại sau',
  'err.locked':
    'Nhập sai mật khẩu quá nhiều lần, tài khoản đã tạm thời bị khóa, vui lòng thử lại sau 15 phút',
  'err.invalidEmail': 'Vui lòng nhập địa chỉ email hợp lệ',
  'err.passwordShort': 'Mật khẩu ít nhất 8 ký tự',
  'err.passwordMismatch': 'Hai lần nhập mật khẩu không khớp',
  'err.network': 'Lỗi mạng, vui lòng kiểm tra mạng rồi thử lại',
  'err.server': 'Dịch vụ tạm thời không khả dụng, vui lòng thử lại sau',
}

const en: Dict = {
  'skip.link': 'Skip to main content',
  'lang.label': 'Language',
  'nav.features': 'Features',
  'nav.how': 'How it works',
  'nav.recipes': 'Recipes',
  'nav.faq': 'FAQ',
  'header.login': 'Sign in',
  'header.register': 'Create account',
  'header.enterApp': 'Open the app',
  'header.menuOpen': 'Open menu',
  'header.menuClose': 'Close menu',
  'header.menuLabel': 'Menu',
  'hero.title': 'Snap one receipt — your fridge and ledger are done.',
  'hero.subtitle':
    'IMSF helps your family manage the fridge, track every expense, and suggests recipes for food about to expire.',
  'hero.vp1': 'Snap a photo — items filed and expenses booked automatically',
  'hero.vp2': 'About to expire? Get a recipe for it',
  'hero.vp3': 'One family, one shared ledger',
  'hero.ctaPrimary': 'Start using it free',
  'hero.ctaSecondary': 'See how it works',
  'hero.mockTitle': 'App preview',
  'hero.mockText': 'Interface preview (mock)',
  'trust.t1': 'Made for families',
  'trust.d1':
    'Designed for a family’s daily cooking, bookkeeping and fridge — not for company reports.',
  'trust.t2': 'No ads',
  'trust.d2':
    'There are no ads in the interface, and nothing is ever pushed at you.',
  'trust.t3': 'Your data is yours',
  'trust.d3': 'Only members of your own household can see your family’s data.',
  'features.f1t': 'Smart receipt scan',
  'features.f1d':
    'Snap a receipt and IMSF reads the items, prices and total. Check it once, then one tap files everything into the fridge and the ledger. Chinese and Vietnamese receipts supported.',
  'features.f1l': 'Learn more',
  'features.f2t': 'Smart fridge',
  'features.f2d':
    'Every ingredient gets a shelf-life reminder. When something is about to expire, IMSF asks one question — answer in one tap: finished it, or keep it three more days.',
  'features.f2l': 'Learn more',
  'features.f3t': 'Family expense book',
  'features.f3d':
    'Write an entry by hand, or let a receipt book itself. Monthly views, totals by category, 14 currencies — each summed on its own, never mixed, never converted.',
  'features.f3l': 'Learn more',
  'features.f4t': 'Community recipes',
  'features.f4d':
    'See what others cooked from food about to expire. Save a recipe you like, cook it, and turn it into a shopping list in one tap.',
  'features.f4l': 'Browse recipes',
  'features.f5t': 'Appliance maintenance',
  'features.f5d':
    'Record each appliance’s purchase date and maintenance cycle, get reminded before it’s due, and look up the full record any time.',
  'features.f5l': 'Learn more',
  'features.mockLabel': 'Interface preview (mock)',
  'how.title': 'How it works',
  'how.s1t': 'Snap the receipt',
  'how.s1d': 'After shopping, snap a photo of the receipt.',
  'how.s2t': 'Filed and booked automatically',
  'how.s2d':
    'IMSF reads the items and checks the total; confirm once and the food goes to the fridge, the spending to the ledger.',
  'how.s3t': 'About to expire? Cook it',
  'how.s3d':
    'When food is about to expire, check the recipe suggestions, cook a dish, and waste nothing.',
  'how.cta': 'Start using it free',
  'video.text': 'Demo video coming soon',
  'reviews.title': 'What families say',
  'reviews.empty':
    'Awaiting real feedback — the first families’ reviews will appear here.',
  'faq.title': 'Frequently asked questions',
  'faq.q1': 'Is IMSF free?',
  'faq.a1':
    'Free for family use. No paid plans, no ads. If a paid feature ever comes, we’ll tell you in advance.',
  'faq.q2': 'Which languages are supported?',
  'faq.a2':
    'The interface is available in Chinese, Vietnamese and English — switch any time at the top right. Chinese and Vietnamese receipts are both recognised.',
  'faq.q3': 'How do I sign in — WeChat or email?',
  'faq.a3':
    'On the website, sign in with email. In the WeChat Mini Program, sign in with WeChat.',
  'faq.q4': 'Where is my data stored, and who can see it?',
  'faq.a4':
    'Your data lives in your household’s own ledger, and only members of the same household can see it. Switch phones or devices — sign in to the same account and it’s there.',
  'faq.q5': 'Can I use it in Vietnam?',
  'faq.a5':
    'Yes. Vietnamese receipts, Vietnamese dong (VND) and a Vietnamese interface are all supported. VND, CNY, USD and the other 11 currencies are each summed separately.',
  'cta.title': 'Start today — one household, one IMSF.',
  'cta.button': 'Start using it free',
  'footer.product': 'Product',
  'footer.start': 'Get started',
  'footer.help': 'Help',
  'footer.legal': 'Legal',
  'footer.features': 'Features',
  'footer.how': 'How it works',
  'footer.recipes': 'Recipes',
  'footer.faq': 'FAQ',
  'footer.register': 'Create account',
  'footer.login': 'Sign in',
  'footer.enterApp': 'Open the app',
  'footer.contact': 'Contact us',
  'footer.privacy': 'Privacy policy',
  'footer.terms': 'Terms of service',
  'footer.tagline': 'IMSF — for a family that keeps its fridge and ledger in order.',
  'legal.privacyTitle': 'Privacy policy',
  'legal.termsTitle': 'Terms of service',
  'legal.contactTitle': 'Contact us',
  'legal.wip': 'Being written',
  'legal.wipText':
    'This page is being written; the finished text will be published here.',
  'legal.contactText': 'Contact details will be published here soon.',
  'legal.back': 'Back to home',
  'auth.loginTitle': 'Sign in',
  'auth.registerTitle': 'Create account',
  'auth.email': 'Email',
  'auth.password': 'Password',
  'auth.confirmPassword': 'Confirm password',
  'auth.name': 'Name (optional)',
  'auth.loginSubmit': 'Sign in',
  'auth.registerSubmit': 'Create account',
  'auth.loadingLogin': 'Signing in…',
  'auth.loadingRegister': 'Creating account…',
  'auth.noAccount': 'Don’t have an account? Create one',
  'auth.hasAccount': 'Already have an account? Sign in',
  'auth.goLogin': 'Sign in now',
  'auth.note':
    'The website supports email sign-in only. To sign in with WeChat, use the Mini Program.',
  'auth.showPassword': 'Show password',
  'auth.hidePassword': 'Hide password',
  'auth.lockedCountdown': 'Locked — retry in {mm}:{ss}',
  'err.invalidCredentials': 'Incorrect email or password',
  'err.emailTaken': 'This email is already registered — please sign in',
  'err.tooFrequent': 'Too many requests — please try again later',
  'err.locked':
    'Too many wrong passwords — this account is temporarily locked, please try again in 15 minutes',
  'err.invalidEmail': 'Please enter a valid email address',
  'err.passwordShort': 'Password must be at least 8 characters',
  'err.passwordMismatch': 'The two passwords don’t match',
  'err.network': 'Network error — please check your connection and try again',
  'err.server': 'Service temporarily unavailable — please try again later',
}

export const DICTS: Record<Language, Dict> = { 'zh-CN': zh, vi, en }

/** Replace `{name}` placeholders in a dictionary string. */
export function fill(template: string, vars: Record<string, string>): string {
  let out = template
  for (const [key, value] of Object.entries(vars)) {
    out = out.replace(`{${key}}`, value)
  }
  return out
}

export interface LanguageContextValue {
  lang: Language
  setLanguage: (lang: Language) => void
  t: Dict
}

export const LanguageContext = createContext<LanguageContextValue>({
  lang: 'zh-CN',
  setLanguage: () => undefined,
  t: zh,
})

export function useLanguage(): LanguageContextValue {
  return useContext(LanguageContext)
}
