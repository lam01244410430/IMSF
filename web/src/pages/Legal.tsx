/**
 * Placeholder legal / contact pages (reform plan §4.8). These pages
 * honestly say the content is still being written — no legal text is
 * fabricated, and no contact address is invented.
 */
import { Link } from 'react-router-dom'
import { useLanguage } from '../lib/i18n'
import { AuthLayout } from '../components/AuthLayout'

export function LegalPage({ kind }: { kind: 'privacy' | 'terms' | 'contact' }) {
  const { t } = useLanguage()
  const title =
    kind === 'privacy'
      ? t['legal.privacyTitle']
      : kind === 'terms'
        ? t['legal.termsTitle']
        : t['legal.contactTitle']
  return (
    <AuthLayout title={title}>
      {kind === 'contact' ? (
        <p className="auth-note">{t['legal.contactText']}</p>
      ) : (
        <>
          <p className="auth-note">{t['legal.wip']}</p>
          <p className="auth-note">{t['legal.wipText']}</p>
        </>
      )}
      <p className="auth-switch">
        <Link to="/">{t['legal.back']}</Link>
      </p>
    </AuthLayout>
  )
}
