/**
 * Account menu (header feature, Lam 2026-11-22): the AppShell topbar
 * had NO account button and NO logout — the user name was plain text
 * and logout lived only on /app/mine. This replaces that span with a
 * clickable account button (the 'mine' icon + display name on
 * desktop, icon-only below 768px) that opens a dropdown menu.
 *
 * The menu is âm tường ("flush with the wall"), like the language
 * panel (LanguageSwitcher): the wrapper is position: static, so the
 * panel anchors to the sticky .app-topbar itself; it shares the
 * topbar's background variable (var(--im-surface) — NOT var(--im-bg),
 * which differs from the topbar in dark mode), has NO box-shadow and
 * no radius, and is separated only by one 1px hairline at its bottom
 * edge. A visible shadow or floating panel is a FAIL.
 *
 * Keyboard (copied from LanguageSwitcher): ArrowDown / Enter / Space
 * on the trigger opens the menu and focuses the first item;
 * ArrowUp / ArrowDown move (wraps), Home / End jump; Escape closes
 * and returns focus to the trigger; Tab closes and focus moves on
 * from the trigger (never trapped). Click/pointerdown outside closes.
 *
 * Logged in: read-only name + email, a link to /app/mine (label 我的,
 * the existing nav label), and a logout button (logout() + navigate
 * '/'). Logged out: the button shows the generic account icon and
 * the menu offers only Log in / Register links.
 */
import { useEffect, useId, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  getStoredUserEmail,
  getStoredUserName,
  isLoggedIn,
  logout,
} from '../lib/auth'
import { useLanguage } from '../lib/i18n'
import { Icon } from './Icon'

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      className={`account-menu-chevron${open ? ' open' : ''}`}
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M4 6l4 4 4-4" />
    </svg>
  )
}

/**
 * Topbar display name (moved from AppShell, Phase 4): the stored name
 * from the login/register response, else the email local part — never
 * the raw user id (UUID) decoded from the JWT.
 */
function getDisplayName(): string | null {
  const name = getStoredUserName()
  if (name) return name
  const email = getStoredUserEmail()
  if (email) {
    const local = email.split('@')[0]?.trim()
    if (local) return local
  }
  return null
}

export function AccountMenu() {
  const { t } = useLanguage()
  const navigate = useNavigate()
  const loggedIn = isLoggedIn()
  const displayName = getDisplayName() ?? (loggedIn ? '用户' : '未登录')
  const email = getStoredUserEmail()
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(0)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const itemRefs = useRef<Array<HTMLAnchorElement | HTMLButtonElement | null>>(
    [],
  )
  const rootRef = useRef<HTMLSpanElement>(null)
  const openViaKeyboard = useRef(false)
  const panelId = useId()

  // Two focusable menu items in either state (the read-only
  // name/email block is not focusable).
  const itemCount = 2

  const openPanel = (viaKeyboard: boolean) => {
    setActiveIndex(0)
    openViaKeyboard.current = viaKeyboard
    setOpen(true)
  }

  const closePanel = (focusTrigger: boolean) => {
    setOpen(false)
    if (focusTrigger) triggerRef.current?.focus()
  }

  const handleLogout = () => {
    logout()
    navigate('/')
  }

  // Keyboard-open moves focus to the first item; mouse-open leaves
  // focus on the trigger.
  useEffect(() => {
    if (open && openViaKeyboard.current) {
      openViaKeyboard.current = false
      itemRefs.current[activeIndex]?.focus()
    }
  }, [open, activeIndex])

  // Click/pointerdown outside closes (the trigger itself is inside
  // the root, so its click still toggles normally).
  useEffect(() => {
    if (!open) return
    const onPointerDown = (event: PointerEvent) => {
      if (
        rootRef.current &&
        !rootRef.current.contains(event.target as Node)
      ) {
        setOpen(false)
      }
    }
    document.addEventListener('pointerdown', onPointerDown)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
    }
  }, [open])

  const focusItem = (index: number) => {
    setActiveIndex(index)
    itemRefs.current[index]?.focus()
  }

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (!open) {
      // Enter / Space on the trigger fire a native click, which the
      // onClick toggle handles; only ArrowDown needs a key handler.
      if (event.key === 'ArrowDown') {
        event.preventDefault()
        openPanel(true)
      }
      return
    }
    if (event.key === 'Escape') {
      event.preventDefault()
      event.stopPropagation()
      closePanel(true)
      return
    }
    if (event.key === 'Tab') {
      // Close and let focus move on naturally from the trigger.
      closePanel(true)
      return
    }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      const dir = event.key === 'ArrowDown' ? 1 : -1
      const next = (activeIndex + dir + itemCount) % itemCount
      focusItem(next)
      return
    }
    if (event.key === 'Home') {
      event.preventDefault()
      focusItem(0)
      return
    }
    if (event.key === 'End') {
      event.preventDefault()
      focusItem(itemCount - 1)
    }
  }

  return (
    <span ref={rootRef} className="account-menu" onKeyDown={onKeyDown}>
      <button
        ref={triggerRef}
        type="button"
        className="account-menu-btn"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={panelId}
        aria-label={t['header.account']}
        onClick={(event) => {
          // A keyboard-triggered click has detail === 0; a mouse
          // click has detail >= 1.
          if (open) {
            closePanel(false)
          } else {
            openPanel(event.detail === 0)
          }
        }}
      >
        <Icon name="mine" className="account-menu-icon" />
        <span className="account-menu-name">{displayName}</span>
        <ChevronIcon open={open} />
      </button>
      {open ? (
        <div
          className="account-panel"
          role="menu"
          id={panelId}
          aria-label={t['header.account']}
        >
          {loggedIn ? (
            <>
              <div className="account-panel-info">
                <span className="account-panel-name">{displayName}</span>
                {email ? (
                  <span className="account-panel-email">{email}</span>
                ) : null}
              </div>
              <div className="account-panel-divider" aria-hidden="true" />
              <Link
                ref={(el) => {
                  itemRefs.current[0] = el
                }}
                to="/app/mine"
                role="menuitem"
                tabIndex={activeIndex === 0 ? 0 : -1}
                className="account-panel-item"
                onClick={() => {
                  closePanel(true)
                }}
              >
                我的
              </Link>
              <button
                ref={(el) => {
                  itemRefs.current[1] = el
                }}
                type="button"
                role="menuitem"
                tabIndex={activeIndex === 1 ? 0 : -1}
                className="account-panel-item"
                onClick={handleLogout}
              >
                {t['header.logout']}
              </button>
            </>
          ) : (
            <>
              <Link
                ref={(el) => {
                  itemRefs.current[0] = el
                }}
                to="/login"
                role="menuitem"
                tabIndex={activeIndex === 0 ? 0 : -1}
                className="account-panel-item"
                onClick={() => {
                  closePanel(true)
                }}
              >
                {t['header.login']}
              </Link>
              <Link
                ref={(el) => {
                  itemRefs.current[1] = el
                }}
                to="/register"
                role="menuitem"
                tabIndex={activeIndex === 1 ? 0 : -1}
                className="account-panel-item"
                onClick={() => {
                  closePanel(true)
                }}
              >
                {t['header.register']}
              </Link>
            </>
          )}
        </div>
      ) : null}
    </span>
  )
}
