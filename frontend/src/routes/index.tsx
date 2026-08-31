import { lazy, Suspense, type ReactNode } from "react";
import AppShell from "@/components/AppShell";
import { AuthModal, ProjectCreateModal, ToastContainer, UploadDrawer } from "@/components";
import { Navigate, RouteParams, matchPath, useLocation, useNavigate } from "@/router";
import { useAuthStore } from "@/stores/authStore";
import { postAuthStartAction } from "@/lib/publicNavigation";

const SiteHome = lazy(() => import("@/views/SiteHome"));
const AuthPage = lazy(() => import("@/views/AuthPage"));
const HomeDashboard = lazy(() => import("@/views/HomeDashboard"));
const LibraryView = lazy(() => import("@/views/LibraryView"));
const ProjectWorkspaceView = lazy(() => import("@/views/ProjectWorkspaceView"));
const InspirationView = lazy(() => import("@/views/InspirationView"));
const AccountCenter = lazy(() => import("@/views/AccountCenter"));
const HelpCenterView = lazy(() => import("@/views/HelpCenterView"));
const WechatCallbackView = lazy(() => import("@/views/WechatCallbackView"));
const NotificationsView = lazy(() => import("@/views/NotificationsView"));
const ProductPreviewView = import.meta.env.DEV
  ? lazy(() => import("@/dev/ProductPreviewView"))
  : null;

function RouteView({ children }: { children: ReactNode }) {
  return <Suspense fallback={<main className="flex min-h-screen items-center justify-center bg-canvas text-sm text-muted">正在加载工作区…</main>}>{children}</Suspense>;
}

function RequireAuth({ children }: { children: ReactNode }) {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const location = useLocation();
  return isAuthenticated ? children : <Navigate to="/" replace state={{ from: location }} />;
}

function WorkspaceLayout({ children }: { children: ReactNode }) {
  return (
    <RequireAuth>
      <AppShell>{children}</AppShell>
      <AuthModal />
      <UploadDrawer />
      <ProjectCreateModal />
    </RequireAuth>
  );
}

function ProjectWorkspaceLayout({ children }: { children: ReactNode }) {
  return (
    <RequireAuth>
      <div className="h-screen overflow-hidden bg-canvas">{children}</div>
      <UploadDrawer />
      <ProjectCreateModal />
      <ToastContainer />
    </RequireAuth>
  );
}

function workspaceView(pathname: string): ReactNode | null {
  if (pathname === "/workspace") return <HomeDashboard />;
  if (pathname === "/workspace/library") return <LibraryView />;
  if (pathname === "/workspace/inspiration") return <InspirationView />;
  if (pathname === "/workspace/help") return <HelpCenterView />;
  if (pathname === "/workspace/account") return <AccountCenter />;
  if (pathname === "/workspace/notifications") return <NotificationsView />;
  return null;
}

export default function AppRouter() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { isAuthenticated, user } = useAuthStore();

  if (pathname === "/") {
    return <RouteView><SiteHome
      isAuthenticated={isAuthenticated}
      membership={user?.membership}
      user={user}
      onOpenAuth={(mode) => navigate(`/${mode}`)}
      onEnterWorkspace={(view = "projects") => {
        const path = view === "help"
          ? "/workspace/help"
          : view === "library"
            ? "/workspace/library"
            : view === "account"
              ? "/workspace/account?section=membership"
              : "/workspace";
        navigate(path);
      }}
      onGoToSite={() => navigate("/", { replace: true })}
      onStartPath={(method) => {
        if (!isAuthenticated) {
          navigate("/register", { state: postAuthStartAction(method) });
          return;
        }
        navigate(`/workspace?create=${method}`);
      }}
    /></RouteView>;
  }
  if (pathname === "/login") return <RouteView><AuthPage mode="login" /></RouteView>;
  if (pathname === "/register") return <RouteView><AuthPage mode="register" /></RouteView>;
  if (pathname === "/auth/wechat/callback") return <RouteView><WechatCallbackView /></RouteView>;
  if (ProductPreviewView && pathname === "/workspace/library/__preview__") {
    return <RouteView><ProductPreviewView type="library" /></RouteView>;
  }
  if (ProductPreviewView && pathname === "/workspace/inspiration/__preview__") {
    return <RouteView><ProductPreviewView type="inspiration" /></RouteView>;
  }
  if (ProductPreviewView && pathname === "/workspace/creation/__preview__") {
    return <RouteView><ProductPreviewView type="creation" /></RouteView>;
  }

  const projectParams = matchPath("/workspace/projects/:projectId", pathname);
  if (projectParams) {
    const previewMode = import.meta.env.DEV && projectParams.projectId === "__preview__";
    return (
      previewMode ? <div className="h-screen overflow-hidden bg-canvas">
        <RouteView><RouteParams params={projectParams}><ProjectWorkspaceView /></RouteParams></RouteView>
      </div> : <ProjectWorkspaceLayout>
        <RouteView><RouteParams params={projectParams}><ProjectWorkspaceView /></RouteParams></RouteView>
      </ProjectWorkspaceLayout>
    );
  }

  const workspace = workspaceView(pathname);
  return workspace
    ? <WorkspaceLayout><RouteView>{workspace}</RouteView></WorkspaceLayout>
    : <Navigate to="/" replace />;
}
