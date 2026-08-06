import { lazy, Suspense, type ReactNode } from "react";
import AppShell from "@/components/AppShell";
import {
  AuthModal,
  UploadDrawer,
  ScriptCreateModal,
  AIScriptModal,
  ProjectCreateModal,
} from "@/components";
import { Navigate, RouteParams, matchPath, useLocation } from "@/router";
import { useAuthStore } from "@/stores/authStore";

const SiteHome = lazy(() => import("@/views/SiteHome"));
const HomeDashboard = lazy(() => import("@/views/HomeDashboard"));
const LibraryView = lazy(() => import("@/views/LibraryView"));
const ScriptCenterView = lazy(() => import("@/views/ScriptCenterView"));
const ScriptDetailView = lazy(() => import("@/views/ScriptDetailView"));
const ProjectDetailView = lazy(() => import("@/views/ProjectDetailView"));
const ProjectEditorView = lazy(() => import("@/views/ProjectEditorView"));
const ProjectsView = lazy(() =>
  import("@/views/SecondaryViews").then((module) => ({ default: module.ProjectsView })),
);
const AccountCenter = lazy(() => import("@/views/AccountCenter"));
const HelpCenterView = lazy(() => import("@/views/HelpCenterView"));
const WechatCallbackView = lazy(() => import("@/views/WechatCallbackView"));
const NotificationsView = lazy(() => import("@/views/NotificationsView"));
const InvitationView = lazy(() => import("@/views/InvitationView"));

function RouteView({ children }: { children: ReactNode }) {
  return (
    <Suspense
      fallback={(
        <main className="flex min-h-screen items-center justify-center bg-canvas text-sm text-muted">
          正在加载工作区…
        </main>
      )}
    >
      {children}
    </Suspense>
  );
}

function RequireAuth({ children }: { children: ReactNode }) {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const location = useLocation();
  if (!isAuthenticated) {
    return <Navigate to="/" replace state={{ from: location }} />;
  }
  return children;
}

function WorkspaceLayout({ children }: { children: ReactNode }) {
  return (
    <RequireAuth>
      <AppShell>{children}</AppShell>
      <AuthModal />
      <UploadDrawer />
      <ScriptCreateModal />
      <AIScriptModal />
      <ProjectCreateModal />
    </RequireAuth>
  );
}

function workspaceView(pathname: string): ReactNode | null {
  if (pathname === "/workspace") return <HomeDashboard />;
  if (pathname === "/workspace/library") return <LibraryView />;
  if (pathname === "/workspace/scripts") return <ScriptCenterView />;
  if (pathname === "/workspace/projects") return <ProjectsView />;
  if (pathname === "/workspace/help") return <HelpCenterView />;
  if (pathname === "/workspace/account") return <AccountCenter />;
  if (pathname === "/workspace/notifications") return <NotificationsView />;

  const projectParams = matchPath("/workspace/projects/:projectId", pathname);
  if (projectParams) {
    return <RouteParams params={projectParams}><ProjectDetailView /></RouteParams>;
  }
  return null;
}

export default function AppRouter() {
  const { pathname } = useLocation();

  if (pathname === "/") {
    return <><RouteView><SiteHome /></RouteView><AuthModal /></>;
  }
  if (pathname === "/workspace/scripts/editor") {
    return <Navigate to="/workspace/scripts" replace />;
  }
  if (pathname === "/workspace/project" || pathname === "/workspace/project/editor") {
    return <Navigate to="/workspace/projects" replace />;
  }

  const scriptEditorParams = matchPath("/workspace/scripts/:scriptId/editor", pathname);
  if (scriptEditorParams) {
    return (
      <RequireAuth>
        <RouteParams params={scriptEditorParams}>
          <RouteView><ScriptDetailView /></RouteView>
        </RouteParams>
      </RequireAuth>
    );
  }

  const projectEditorParams = matchPath("/workspace/projects/:projectId/editor", pathname);
  if (projectEditorParams) {
    return (
      <RequireAuth>
        <RouteParams params={projectEditorParams}>
          <RouteView><ProjectEditorView /></RouteView>
        </RouteParams>
        <UploadDrawer />
      </RequireAuth>
    );
  }

  const workspace = workspaceView(pathname);
  if (workspace) {
    return <WorkspaceLayout><RouteView>{workspace}</RouteView></WorkspaceLayout>;
  }

  if (pathname === "/auth/wechat/callback") {
    return <RouteView><WechatCallbackView /></RouteView>;
  }

  const invitationParams = matchPath("/invite/:token", pathname);
  if (invitationParams) {
    return (
      <RouteParams params={invitationParams}>
        <RouteView><InvitationView /></RouteView>
        <AuthModal />
      </RouteParams>
    );
  }

  return <Navigate to="/" replace />;
}
