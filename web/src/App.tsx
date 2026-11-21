import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import { PublicOnly, RequireAuth } from './components/guards'
import { BlogPage } from './pages/Blog'
import { BlogPostPage } from './pages/BlogPost'
import { KnowledgePage } from './pages/Knowledge'
import { LandingPage } from './pages/Landing'
import { LegalPage } from './pages/Legal'
import { LoginPage } from './pages/Login'
import { NotFoundPage } from './pages/NotFound'
import { RegisterPage } from './pages/Register'
import { FridgePage } from './pages/app/Fridge'
import { MaintenancePage } from './pages/app/Maintenance'
import { MinePage } from './pages/app/Mine'
import { ReceiptDetailPage } from './pages/app/ReceiptDetail'
import { ReceiptsPage } from './pages/app/Receipts'
import { SpendingPage } from './pages/app/Spending'
import { TransactionsPage } from './pages/app/Transactions'
import { UploadPage } from './pages/app/Upload'
import { LanguageProvider } from './lib/LanguageProvider'

/**
 * Routes (reform plan §3.2):
 *   /            public landing (Wave 2: hero, trust, features,
 *                how-it-works, FAQ, reviews, footer)
 *   /login       public email login (Wave 2)
 *   /register    public email registration (Wave 2)
 *   /app/*       guarded — unauthenticated → /login?next=<path>
 *   /blog        public recipe list (placeholder; Wave 2)
 *   /blog/:id    public recipe article (placeholder; Wave 2)
 *   /knowledge   knowledge search (plan §6.3: blog ingredient links
 *                point here with ?q=<canonical name>; the endpoint
 *                needs auth, so logged-out visitors are sent to
 *                /login with a notice — Wave 3 fix)
 *   /privacy /terms /contact — honest placeholder pages (§4.8):
 *                "being written", no fabricated legal text.
 *   *            404 catch-all
 *
 * /app redirects to /app/upload (the Mini Program's post-login
 * destination, plan §3.2 Q2 decided) and the 首页 sidebar item points
 * to /app/upload. Recipes live at /blog (plan §5.3); the sidebar
 * 菜谱 item already points there. /recipes and /app/recipes both
 * redirect to /blog (plan §10 Q9) so the old URLs never 404.
 * /app/receipts and /app/receipts/:id are NOT in the sidebar; they are
 * reached from the upload page and from receipt rows.
 * /app/maintenance is NOT in the sidebar; it is linked from 我的.
 * Shopping lists are NOT built in this wave (no route in §3.2).
 */
export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route
        path="/login"
        element={
          <PublicOnly>
            <LoginPage />
          </PublicOnly>
        }
      />
      <Route
        path="/register"
        element={
          <PublicOnly>
            <RegisterPage />
          </PublicOnly>
        }
      />
      <Route
        path="/app/*"
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route index element={<Navigate to="/app/upload" replace />} />
        <Route path="upload" element={<UploadPage />} />
        <Route path="fridge" element={<FridgePage />} />
        <Route path="transactions" element={<TransactionsPage />} />
        <Route path="spending" element={<SpendingPage />} />
        <Route path="maintenance" element={<MaintenancePage />} />
        <Route path="receipts" element={<ReceiptsPage />} />
        <Route path="receipts/:id" element={<ReceiptDetailPage />} />
        <Route path="mine" element={<MinePage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
      <Route path="/blog" element={<BlogPage />} />
      <Route path="/blog/:id" element={<BlogPostPage />} />
      {/* Plan §10 Q9: /recipes redirects to /blog. */}
      <Route path="/recipes" element={<Navigate to="/blog" replace />} />
      {/* Old Taro URL: /app/recipes redirects to /blog too.
          Top-level (not nested under /app/*) so the static route
          outranks the /app/* splat and /blog stays public. */}
      <Route path="/app/recipes" element={<Navigate to="/blog" replace />} />
      <Route path="/knowledge" element={<KnowledgePage />} />
      <Route path="/privacy" element={<LegalPage kind="privacy" />} />
      <Route path="/terms" element={<LegalPage kind="terms" />} />
      <Route path="/contact" element={<LegalPage kind="contact" />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}

export default function App() {
  return (
    <LanguageProvider>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </LanguageProvider>
  )
}
