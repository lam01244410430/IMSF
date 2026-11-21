/**
 * Language switcher (Dashboard Phase A, D4): a custom dropdown panel
 * replacing the native <select> — 3 columns on desktop, 1 column in
 * the mobile drawer, language name + short code (EN / 中文 / VI) +
 * tick on the selected language.
 *
 * The panel is âm tường ("flush with the wall"): it anchors to the
 * header itself (the wrapper is position: static — see index.css),
 * shares the header's background variable, has NO box-shadow and no
 * radius, and is separated only by one 1px hairline. The notification
 * panel (.notif-panel) is the one exception — it is a floating card
 * and keeps its shadow; do NOT copy its treatment here.
 *
 * Keyboard (the native <select> gave this for free, so it is rebuilt
 * here): ArrowDown / Enter / Space on the trigger opens the panel
 * and focuses the selected option; ArrowUp / ArrowDown move (wraps),
 * Home / End jump; Enter / Space selects; Escape closes and returns
 * focus to the trigger; Tab closes and focus moves on from the
 * trigger (never trapped). Escape inside the drawer closes the
 * language panel first — the wrapper keydown handler stops
 * propagation, so the drawer's document-level Escape listener (which
 * closes the drawer) never sees it.
 *
 * The export name and props ({ id?, className? }) are unchanged, so
 * all 6 call sites keep working.
 */
import { useEffect, useId, useRef, useState } from 'react'
import { LANGUAGES, useLanguage, type Language } from '../lib/i18n'

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      className={`lang-switcher-chevron${open ? ' open' : ''}`}
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

function TickIcon() {
  return (
    <svg
      className="lang-option-tick"
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
      <path d="M3 8.5 6.5 12 13 4.5" />
    </svg>
  )
}

export function LanguageSwitcher({
  id,
  className,
}: {
  id?: string
  className?: string
}) {
  const { lang, setLanguage, t } = useLanguage()
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(() =>
    Math.max(
      0,
      LANGUAGES.findIndex((option) => option.code === lang),
    ),
  )
  const triggerRef = useRef<HTMLButtonElement>(null)
  const optionRefs = useRef<Array<HTMLButtonElement | null>>([])
  const rootRef = useRef<HTMLSpanElement>(null)
  const openViaKeyboard = useRef(false)
  const panelId = useId()

  const current =
    LANGUAGES.find((option) => option.code === lang) ?? LANGUAGES[0]
  const currentIndex = Math.max(
    0,
    LANGUAGES.findIndex((option) => option.code === lang),
  )

  const openPanel = (viaKeyboard: boolean) => {
    setActiveIndex(currentIndex)
    openViaKeyboard.current = viaKeyboard
    setOpen(true)
  }

  const closePanel = (focusTrigger: boolean) => {
    setOpen(false)
    if (focusTrigger) triggerRef.current?.focus()
  }

  const select = (code: Language) => {
    setLanguage(code)
    closePanel(true)
  }

  // Keyboard-open moves focus to the selected option; mouse-open
  // leaves focus on the trigger.
  useEffect(() => {
    if (open && openViaKeyboard.current) {
      openViaKeyboard.current = false
      optionRefs.current[activeIndex]?.focus()
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
  }, [open ])

  const focusOption = (index: number) => {
    setActiveIndex(index)
    optionRefs.current[index]?.focus()
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
      // Stop here so the drawer's document-level Escape listener
      // (which closes the drawer) does not also fire: one Escape
      // closes the panel, a second closes the drawer.
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
      const next =
        (activeIndex + dir + LANGUAGES.length) % LANGUAGES.length
      focusOption(next)
      return
    }
    if (event.key === 'Home') {
      event.preventDefault()
      focusOption(0)
      return
    }
    if (event.key === 'End') {
      event.preventDefault()
      focusOption(LANGUAGES.length - 1)
    }
  }

  return (
    <span
      ref={rootRef}
      className={className ?? 'lang-switcher'}
      onKeyDown={onKeyDown}
    >
      <button
        ref={triggerRef}
        type="button"
        id={id}
        className="lang-switcher-btn"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={panelId}
        aria-label={t['lang.label']}
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
        <span className="lang-switcher-code">{current.short}</span>
        <ChevronIcon open={open} />
      </button>
      {open ? (
        <div
          className="lang-panel"
          role="menu"
          id={panelId}
          aria-label={t['lang.choose']}
        >
          <ul className="lang-panel-grid">
            {LANGUAGES.map((option, i) => (
              <li key={option.code}>
                <button
                  ref={(el) => {
                    optionRefs.current[i] = el
                  }}
                  type="button"
                  role="menuitemradio"
                  aria-checked={lang === option.code}
                  tabIndex={activeIndex === i ? 0 : -1}
                  className="lang-option"
                  onClick={() => {
                    select(option.code)
                  }}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      // preventDefault stops the native click that
                      // Enter/Space would also fire on the button.
                      event.preventDefault()
                      select(option.code)
                    }
                  }}
                >
                  <span className="lang-option-name">{option.label}</span>
                  <span className="lang-option-code">{option.short}</span>
                  {lang === option.code ? <TickIcon /> : null}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </span>
  )
}
