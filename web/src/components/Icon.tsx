/**
 * Self-hosted SVG icons (web/src/assets/icons/). No icon font, no CDN,
 * no emoji. Each file uses stroke="currentColor", so the colour comes
 * from CSS (`color` on the nav item: resting #5F6368, active #C2410C).
 * Rendered at 20px from a 24px viewBox; stroke 1.5px.
 */
import editUrl from '../assets/icons/edit.svg'
import fridgeUrl from '../assets/icons/fridge.svg'
import homeUrl from '../assets/icons/home.svg'
import listUrl from '../assets/icons/list.svg'
import mineUrl from '../assets/icons/mine.svg'
import recipesUrl from '../assets/icons/recipes.svg'

export type IconName = 'home' | 'fridge' | 'recipes' | 'mine' | 'edit' | 'list'

const ICON_URLS: Record<IconName, string> = {
  home: homeUrl,
  fridge: fridgeUrl,
  recipes: recipesUrl,
  mine: mineUrl,
  edit: editUrl,
  list: listUrl,
}

export function Icon({ name, className }: { name: IconName; className?: string }) {
  return (
    <svg className={className} aria-hidden="true" focusable="false">
      <use href={ICON_URLS[name]} />
    </svg>
  )
}
