import { Link, useNavigate } from 'react-router-dom'
import { isLoggedIn, logout } from '../lib/auth'

/**
 * Landing placeholder (Wave 2 builds the full landing: hero, trust
 * block, features, how-it-works, FAQ, reviews, footer).
 *
 * Header state is already correct per plan §3.2/§4.1: unauthenticated
 * shows 登录 / 注册; authenticated shows 进入应用 instead. The four
 * menu items are 功能 / 使用方法 / 菜谱 / 常见问题.
 */
export function LandingPage() {
  const authed = isLoggedIn()
  const navigate = useNavigate()
  return (
    <div>
      <header className="landing-header">
        <Link to="/" className="landing-brand">
          IMSF
        </Link>
        <nav className="landing-menu" aria-label="主导航">
          <a href="#features">功能</a>
          <a href="#how-it-works">使用方法</a>
          <Link to="/blog">菜谱</Link>
          <a href="#faq">常见问题</a>
        </nav>
        <span className="landing-header-spacer" />
        <span className="landing-lang">中文</span>
        {authed ? (
          <>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => {
                logout()
                navigate('/')
              }}
            >
              退出
            </button>
            <Link to="/app" className="btn btn-primary btn-sm">
              进入应用
            </Link>
          </>
        ) : (
          <>
            <Link to="/login" className="btn btn-ghost btn-sm">
              登录
            </Link>
            <Link to="/register" className="btn btn-primary btn-sm">
              注册
            </Link>
          </>
        )}
      </header>
      <main className="placeholder-page" style={{ padding: 24 }}>
        <h1>Landing</h1>
        <p>Placeholder — the full landing page is built in Wave 2.</p>
      </main>
    </div>
  )
}
