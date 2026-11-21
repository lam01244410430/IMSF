/**
 * Landing page (reform plan §4) — Header → Hero → Trust block →
 * Features → How-it-works → Video demo (slot) → Reviews (honest
 * placeholder) → FAQ → final CTA → Footer.
 *
 * Honesty rules enforced here, per the plan:
 * - No fake screenshots: feature visuals are grey mock frames
 *   labelled as mocks until real screenshots exist. The hero is a
 *   solid dark band (Dashboard Phase A) — no visual, no mock.
 * - No fake reviews: exactly 3 empty slots with the honest text.
 * - No fake video: a 16:9 placeholder, no fake play button.
 * - No fabricated legal text or contact address: legal links go to
 *   placeholder pages that say so.
 * - No fake numbers, no company name, no copyright year.
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import logoUrl from '../assets/logo.svg'
import logoDarkUrl from '../assets/logo-dark.svg'
import { getStoredUserName, isLoggedIn } from '../lib/auth'
import { useLanguage, type Dict } from '../lib/i18n'
import { useTheme } from '../lib/theme'
import { LanguageSwitcher } from '../components/LanguageSwitcher'
import { ThemeToggle } from '../components/ThemeToggle'

function CheckIcon() {
  return (
    <svg
      className="check-icon"
      width="20"
      height="20"
      viewBox="0 0 20 20"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <path
        d="M4 10.5 8.5 15 16 5.5"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      className={`faq-chevron${open ? ' open' : ''}`}
      width="20"
      height="20"
      viewBox="0 0 20 20"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <path
        d="M5 7.5 10 12.5 15 7.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

interface FeatureDef {
  title: keyof Dict
  desc: keyof Dict
  link: keyof Dict
  /** App page when logged in (recipes always goes to /blog). */
  appTo: string
  /** Public target when logged out. */
  publicTo: string
}

const FEATURES: FeatureDef[] = [
  {
    title: 'features.f1t',
    desc: 'features.f1d',
    link: 'features.f1l',
    appTo: '/app/upload',
    publicTo: '#how-it-works',
  },
  {
    title: 'features.f2t',
    desc: 'features.f2d',
    link: 'features.f2l',
    appTo: '/app/fridge',
    publicTo: '#how-it-works',
  },
  {
    title: 'features.f3t',
    desc: 'features.f3d',
    link: 'features.f3l',
    appTo: '/app/transactions',
    publicTo: '#how-it-works',
  },
  {
    title: 'features.f4t',
    desc: 'features.f4d',
    link: 'features.f4l',
    appTo: '/blog',
    publicTo: '/blog',
  },
  {
    title: 'features.f5t',
    desc: 'features.f5d',
    link: 'features.f5l',
    appTo: '/app/maintenance',
    publicTo: '#how-it-works',
  },
]

function FeatureLink({
  feature,
  authed,
  label,
}: {
  feature: FeatureDef
  authed: boolean
  label: string
}) {
  const to = authed ? feature.appTo : feature.publicTo
  const text = `${label} →`
  if (to.startsWith('#')) {
    return (
      <a href={to} className="feature-link">
        {text}
      </a>
    )
  }
  return (
    <Link to={to} className="feature-link">
      {text}
    </Link>
  )
}

const FAQ_KEYS = [
  { q: 'faq.q1', a: 'faq.a1' },
  { q: 'faq.q2', a: 'faq.a2' },
  { q: 'faq.q3', a: 'faq.a3' },
  { q: 'faq.q4', a: 'faq.a4' },
  { q: 'faq.q5', a: 'faq.a5' },
] as const

function LandingHeader() {
  const { t } = useLanguage()
  const { theme } = useTheme()
  const authed = isLoggedIn()
  const userName = getStoredUserName()
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
        <img
          src={theme === 'dark' ? logoDarkUrl : logoUrl}
          alt="IMSF"
          className="landing-logo"
        />
      </Link>
      <nav className="landing-menu" aria-label={t['header.menuLabel']}>
        <a href="#features">{t['nav.features']}</a>
        <a href="#how-it-works">{t['nav.how']}</a>
        <Link to="/blog">{t['nav.recipes']}</Link>
        <a href="#faq">{t['nav.faq']}</a>
      </nav>
      <span className="landing-header-spacer" />
      <ThemeToggle />
      <LanguageSwitcher className="lang-switcher landing-lang-desktop" />
      {authed ? (
        <>
          {userName ? (
            <span className="landing-user-name">{userName}</span>
          ) : null}
          <Link to="/app" className="landing-register">
            {t['header.enterApp']}
          </Link>
        </>
      ) : (
        <>
          <Link to="/login" className="landing-login">
            {t['header.login']}
          </Link>
          <Link to="/register" className="landing-register">
            {t['header.register']}
          </Link>
        </>
      )}
      <button
        type="button"
        className="landing-hamburger"
        aria-expanded={drawerOpen}
        aria-controls="landing-drawer"
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
            id="landing-drawer"
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
            <div className="drawer-theme-row">
              <span>{t['theme.label']}</span>
              <ThemeToggle />
            </div>
            <LanguageSwitcher className="lang-switcher" />
            <nav
              className="landing-drawer-nav"
              aria-label={t['header.menuLabel']}
            >
              <a href="#features" onClick={closeDrawer}>
                {t['nav.features']}
              </a>
              <a href="#how-it-works" onClick={closeDrawer}>
                {t['nav.how']}
              </a>
              <Link to="/blog" onClick={closeDrawer}>
                {t['nav.recipes']}
              </Link>
              <a href="#faq" onClick={closeDrawer}>
                {t['nav.faq']}
              </a>
            </nav>
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

export function LandingPage() {
  const { t } = useLanguage()
  const authed = isLoggedIn()
  const [openFaq, setOpenFaq] = useState<number | null>(null)

  return (
    <div className="landing-page">
      <a className="skip-link" href="#main">
        {t['skip.link']}
      </a>
      <LandingHeader />
      <main id="main">
        <section className="landing-hero-band" aria-labelledby="hero-title">
          <div className="landing-hero-inner">
            <h1 id="hero-title">{t['hero.title']}</h1>
            <p className="hero-subtitle">{t['hero.subtitle']}</p>
            <ul className="hero-values">
              <li>
                <CheckIcon />
                <span>{t['hero.vp1']}</span>
              </li>
              <li>
                <CheckIcon />
                <span>{t['hero.vp2']}</span>
              </li>
              <li>
                <CheckIcon />
                <span>{t['hero.vp3']}</span>
              </li>
            </ul>
            <div className="hero-cta">
              <Link to="/register" className="cta-primary">
                {t['hero.ctaPrimary']}
              </Link>
              <a href="#how-it-works" className="cta-secondary">
                {t['hero.ctaSecondary']}
              </a>
            </div>
          </div>
        </section>

        <section className="landing-trust" aria-label={t['trust.t1']}>
          <div className="trust-inner">
            <div>
              <h2 className="trust-title">{t['trust.t1']}</h2>
              <p className="trust-text">{t['trust.d1']}</p>
            </div>
            <div>
              <h2 className="trust-title">{t['trust.t2']}</h2>
              <p className="trust-text">{t['trust.d2']}</p>
            </div>
            <div>
              <h2 className="trust-title">{t['trust.t3']}</h2>
              <p className="trust-text">{t['trust.d3']}</p>
            </div>
          </div>
        </section>

        <section
          id="features"
          className="landing-features"
          aria-label={t['nav.features']}
        >
          {FEATURES.map((feature, index) => (
            <div
              key={feature.title}
              className={`feature-block${index % 2 === 1 ? ' reverse' : ''}`}
            >
              <div className="feature-text">
                <h2>{t[feature.title]}</h2>
                <p>{t[feature.desc]}</p>
                <FeatureLink
                  feature={feature}
                  authed={authed}
                  label={t[feature.link]}
                />
              </div>
              <div
                className="feature-visual"
                role="img"
                aria-label={`${t[feature.title]} — ${t['features.mockLabel']}`}
              >
                <div className="mock-frame">
                  <span>{t['features.mockLabel']}</span>
                </div>
              </div>
            </div>
          ))}
        </section>

        <section
          id="how-it-works"
          className="landing-how"
          aria-labelledby="how-title"
        >
          <h2 id="how-title">{t['how.title']}</h2>
          <div className="how-steps">
            <div className="how-step">
              <p className="how-num" aria-hidden="true">
                1
              </p>
              <h3>{t['how.s1t']}</h3>
              <p>{t['how.s1d']}</p>
            </div>
            <div className="how-step">
              <p className="how-num" aria-hidden="true">
                2
              </p>
              <h3>{t['how.s2t']}</h3>
              <p>{t['how.s2d']}</p>
            </div>
            <div className="how-step">
              <p className="how-num" aria-hidden="true">
                3
              </p>
              <h3>{t['how.s3t']}</h3>
              <p>{t['how.s3d']}</p>
            </div>
          </div>
          <Link to="/register" className="feature-link">
            {`${t['how.cta']} →`}
          </Link>
        </section>

        <section className="landing-video" aria-label={t['video.text']}>
          <div className="video-slot">
            <span>{t['video.text']}</span>
          </div>
        </section>

        <section className="landing-reviews" aria-labelledby="reviews-title">
          <h2 id="reviews-title">{t['reviews.title']}</h2>
          <div className="review-slots">
            {[0, 1, 2].map((slot) => (
              <div key={slot} className="review-slot">
                <p>{t['reviews.empty']}</p>
              </div>
            ))}
          </div>
        </section>

        <section
          id="faq"
          className="landing-faq"
          aria-labelledby="faq-title"
        >
          <h2 id="faq-title">{t['faq.title']}</h2>
          {FAQ_KEYS.map((item, index) => {
            const open = openFaq === index
            return (
              <div key={item.q} className="faq-item">
                <button
                  type="button"
                  className="faq-question"
                  id={`faq-button-${index}`}
                  aria-expanded={open}
                  aria-controls={`faq-panel-${index}`}
                  onClick={() => {
                    setOpenFaq(open ? null : index)
                  }}
                >
                  <span>{t[item.q]}</span>
                  <ChevronIcon open={open} />
                </button>
                {open ? (
                  <p
                    id={`faq-panel-${index}`}
                    className="faq-answer"
                    role="region"
                    aria-labelledby={`faq-button-${index}`}
                  >
                    {t[item.a]}
                  </p>
                ) : null}
              </div>
            )
          })}
        </section>

        <section className="landing-cta" aria-labelledby="cta-title">
          <h2 id="cta-title">{t['cta.title']}</h2>
          <Link to="/register" className="cta-primary">
            {t['cta.button']}
          </Link>
        </section>
      </main>

      <footer className="landing-footer">
        <div className="footer-cols">
          <nav aria-label={t['footer.product']}>
            <h2 className="footer-col-title">{t['footer.product']}</h2>
            <ul>
              <li>
                <a href="#features">{t['footer.features']}</a>
              </li>
              <li>
                <a href="#how-it-works">{t['footer.how']}</a>
              </li>
              <li>
                <Link to="/blog">{t['footer.recipes']}</Link>
              </li>
              <li>
                <a href="#faq">{t['footer.faq']}</a>
              </li>
            </ul>
          </nav>
          <nav aria-label={t['footer.start']}>
            <h2 className="footer-col-title">{t['footer.start']}</h2>
            <ul>
              <li>
                <Link to="/register">{t['footer.register']}</Link>
              </li>
              <li>
                <Link to="/login">{t['footer.login']}</Link>
              </li>
              <li>
                <Link to="/app">{t['footer.enterApp']}</Link>
              </li>
            </ul>
          </nav>
          <nav aria-label={t['footer.help']}>
            <h2 className="footer-col-title">{t['footer.help']}</h2>
            <ul>
              <li>
                <a href="#faq">{t['footer.faq']}</a>
              </li>
              <li>
                <Link to="/contact">{t['footer.contact']}</Link>
              </li>
            </ul>
          </nav>
          <nav aria-label={t['footer.legal']}>
            <h2 className="footer-col-title">{t['footer.legal']}</h2>
            <ul>
              <li>
                <Link to="/privacy">{t['footer.privacy']}</Link>
              </li>
              <li>
                <Link to="/terms">{t['footer.terms']}</Link>
              </li>
            </ul>
          </nav>
        </div>
        <div className="footer-bottom">
          <p className="footer-tagline">{t['footer.tagline']}</p>
          <LanguageSwitcher className="lang-switcher" />
        </div>
      </footer>
    </div>
  )
}
