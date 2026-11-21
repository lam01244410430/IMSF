import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import logoUrl from '../assets/logo.svg'
import { isLoggedIn, logout } from '../lib/auth'
import { useLanguage } from '../lib/i18n'
import { LanguageSwitcher } from './LanguageSwitcher'

/**
 * Public header shared by the blog pages (/blog, /blog/:id) and
 * /knowledge.
 *
 * Same structure as the landing header (plan §4.1): logo + name + the
 * 4 menu items (功能 / 使用方法 / 菜谱 / 常见问题) on the left;
 * language + 登录 / 注册 (or 进入应用 when logged in) on the right.
 * Below 768px the menu + auth move into a drawer (same pattern as
 * the landing header: hamburger, Escape to close, overlay click to
 * close); the desktop switcher + auth are hidden by CSS. This
 * component must not drift from the landing header (same classes,
 * same labels) — Phase 4, F-02/F-03/F-04.
 */
export function PublicHeader() {
  const { t } = useLanguage()
  const authed = isLoggedIn()
  const navigate = useNavigate()
  const [drawerOpen, setDrawerOpen] = useState(false)

  useEffect(() => {
    if (!drawerOpen) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setDrawerOpen(false)
    }
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [drawerOpen])

  const closeDrawer = () => {
    setDrawerOpen(false)
  }

  return (
    <header className="landing-header">
      <Link to="/" className="landing-brand" aria-label="IMSF">
        <img src={logoUrl} alt="IMSF" className="landing-logo" />
      </Link>
      <nav className="landing-menu" aria-label={t['header.menuLabel']}>
        <a href="/#features">{t['nav.features']}</a>
        <a href="/#how-it-works">{t['nav.how']}</a>
        <Link to="/blog">{t['nav.recipes']}</Link>
        <a href="/#faq">{t['nav.faq']}</a>
      </nav>
      <span className="landing-header-spacer" />
      <LanguageSwitcher className="lang-switcher landing-lang-desktop" />
      <span className="public-header-auth">
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
              {t['header.logout']}
            </button>
            <Link to="/app" className="btn btn-primary btn-sm">
              {t['header.enterApp']}
            </Link>
          </>
        ) : (
          <>
            <Link to="/login" className="btn btn-ghost btn-sm">
              {t['header.login']}
            </Link>
            <Link to="/register" className="btn btn-primary btn-sm">
              {t['header.register']}
            </Link>
          </>
        )}
      </span>
      <button
        type="button"
        className="landing-hamburger"
        aria-expanded={drawerOpen}
        aria-controls="public-drawer"
        aria-label={
          drawerOpen ? t['header.menuClose'] : t['header.menuOpen']
        }
        onClick={() => {
          setDrawerOpen((open) => !open)
        }}
      >
        {drawerOpen ? '✕' : '☰'}
      </button>
      {drawerOpen ? (
        <>
          <div
            className="landing-drawer-overlay"
            aria-hidden="true"
            onClick={closeDrawer}
          />
          <div
            id="public-drawer"
            className="landing-drawer"
            role="dialog"
            aria-label={t['header.menuLabel']}
          >
            <button
              type="button"
              className="landing-drawer-close"
              aria-label={t['header.menuClose']}
              onClick={closeDrawer}
            >
              ✕
            </button>
            <nav
              className="landing-drawer-nav"
              aria-label={t['header.menuLabel']}
            >
              <a href="/#features" onClick={closeDrawer}>
                {t['nav.features']}
              </a>
              <a href="/#how-it-works" onClick={closeDrawer}>
                {t['nav.how']}
              </a>
              <Link to="/blog" onClick={closeDrawer}>
                {t['nav.recipes']}
              </Link>
              <a href="/#faq" onClick={closeDrawer}>
                {t['nav.faq']}
              </a>
            </nav>
            <LanguageSwitcher className="lang-switcher" />
            {authed ? (
              <Link
                to="/app"
                className="landing-register"
                onClick={closeDrawer}
              >
                {t['header.enterApp']}
              </Link>
            ) : (
              <>
                <Link
                  to="/login"
                  className="landing-login"
                  onClick={closeDrawer}
                >
                  {t['header.login']}
                </Link>
                <Link
                  to="/register"
                  className="landing-register"
                  onClick={closeDrawer}
                >
                  {t['header.register']}
                </Link>
              </>
            )}
          </div>
        </>
      ) : null}
    </header>
  )
}
