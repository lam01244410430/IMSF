import { useLanguage } from '../lib/i18n'
import { sourceSiteName } from '../lib/recipes'

/**
 * Recipe source credit line (blog attribution).
 *
 * Renders the source label + a link to the original recipe. Returns
 * nothing when the recipe has no source_url -- a source is never
 * invented. The link opens in a new tab so the reader does not lose
 * the article.
 */
export function RecipeSource({
  sourceUrl,
  className,
}: {
  sourceUrl: string | null | undefined
  className?: string
}) {
  const { t } = useLanguage()
  if (!sourceUrl) return null
  return (
    <p className={className ? `blog-source ${className}` : 'blog-source'}>
      {t['blog.source']}
      <a href={sourceUrl} target="_blank" rel="noopener noreferrer">
        {sourceSiteName(sourceUrl)}
      </a>
    </p>
  )
}
