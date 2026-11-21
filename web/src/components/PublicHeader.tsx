import { Link, useNavigate } from 'react-router-dom'
import { isLoggedIn, logout } from '../lib/auth'

/**
 * Public header shared by the blog pages (/blog, /blog/:id).
 *
 * Same structure as the landing header placeholder (plan §4.1):
 * logo + name + the 4 menu items (功能 / 使用方法 / 菜谱 / 常见问题)
 * on the left; language + 登录 / 注册 (or 进入应用 when logged in)
 * on the right. The landing page keeps its own inline copy until
 * Wave 2 builds the full landing; this component must not drift
 * from it (same classes, same labels).
 */
export function PublicHeader() {
  const authed = isLoggedIn()
  const navigate = useNavigate()
  return (
    <header className="landing-header">
      <Link to="/" className="landing-brand">
        IMSF
      </Link>
      <nav className="landing-menu" aria-label="主导航">
        <a href="/#features">功能</a>
        <a href="/#how-it-works">使用方法</a>
        <Link to="/blog">菜谱</Link>
        <a href="/#faq">常见问题</a>
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
  )
}
