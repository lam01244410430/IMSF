import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AdminShell, RequireAdmin } from './components/AdminShell'
import { AppShell } from './components/AppShell'
import { PublicOnly, RequireAuth } from './components/guards'
import { AdminAuditPage } from './pages/admin/Audit'
import { AdminOverviewPage } from './pages/admin/Overview'
import { AdminRecipesPage } from './pages/admin/Recipes'
import { AdminSystemPage } from './pages/admin/System'
import { AdminUserDetailPage } from './pages/admin/UserDetail'
import { AdminUsersPage } from './pages/admin/Users'
import { BlogPage } from './pages/Blog'
import { BlogPostPage } from './pages/BlogPost'
import { KnowledgePage } from './pages/Knowledge'
import { LandingPage } from './pages/Landing'
import { LegalPage } from './pages/Legal'
import { LoginPage } from './pages/Login'
import { NotFoundPage } from './pages/NotFound'
import { RegisterPage } from './pages/Register'
import { DashboardPage } from './pages/app/Dashboard'
import { FridgePage } from './pages/app/Fridge'
import { MaintenancePage } from './pages/app/Maintenance'
import { MinePage } from './pages/app/Mine'
import { ReceiptDetailPage } from './pages/app/ReceiptDetail'
import { ReceiptsPage } from './pages/app/Receipts'
import { SpendingPage } from './pages/app/Spending'
import { TransactionsPage } from './pages/app/Transactions'
import { UploadPage } from './pages/app/Upload'
import { LanguageProvider } from './lib/LanguageProvider'
import { ThemeProvider } from './lib/ThemeProvider'

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
 * /app redirects to /app/dashboard (Dashboard Phase B, D1 — this
 * changes the reform plan §3.2 Q2 decision: the dashboard, not
 * /app/upload, is the post-login destination). The sidebar's first
 * item is 仪表盘 → /app/dashboard (icon 'home'); there is no 首页
 * nav item any more — /app/upload stays reachable via the sidebar
 * 拍照 button + the mobile FAB. Recipes live at /blog (plan §5.3);
 * the sidebar 菜谱 item already points there. /recipes and
 * /app/recipes both redirect to /blog (plan §10 Q9) so the old URLs
 * never 404.
 * /app/receipts and /app/receipts/:id are NOT in the sidebar; they are
 * reached from the upload page and from receipt rows.
 * /app/maintenance is NOT in the sidebar; it is linked from 我的.
 * Shopping lists are NOT built in this wave (no route in §3.2).
 *
 * /admin/* (Dashboard Phase C, plan §4 + contract §5): the admin
 * dashboard — own shell (AdminShell), NOT the user AppShell, with a
 * persistent "Admin / 管理后台" banner + a "Return to family app"
 * link to /app/dashboard. Guarded by RequireAdmin (GET
 * /api/v2/admin/me on mount: 401 → /login, 403 → a plain "no access"
 * page). The admin link on 我的 is shown only when that same /me
 * check says admin (see Mine.tsx) — the user sidebar is unchanged.
 * Backend enforcement is the `require_admin` dependency
 * (`IMSF_ADMIN_USER_IDS` allowlist); the frontend guard only
 * decides what to show.
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
        <Route index element={<Navigate to="/app/dashboard" replace />} />
        <Route path="dashboard" element={<DashboardPage />} />
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
      <Route
        path="/admin/*"
        element={
          <RequireAdmin>
            <AdminShell />
          </RequireAdmin>
        }
      >
        <Route index element={<AdminOverviewPage />} />
        <Route path="users" element={<AdminUsersPage />} />
        <Route path="users/:id" element={<AdminUserDetailPage />} />
        <Route path="recipes" element={<AdminRecipesPage />} />
        <Route path="system" element={<AdminSystemPage />} />
        <Route path="audit" element={<AdminAuditPage />} />
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
      <ThemeProvider>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </ThemeProvider>
    </LanguageProvider>
  )
}
