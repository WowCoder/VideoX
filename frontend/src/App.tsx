import { useEffect } from "react";
import { RouterProvider } from "@/router";
import AppRouter from "@/routes";
import { useAuthStore } from "@/stores/authStore";
import { AppErrorBoundary } from "@/components/AppErrorBoundary";

export default function App() {
  const initialized = useAuthStore((s) => s.initialized);
  const loadFromStorage = useAuthStore((s) => s.loadFromStorage);

  useEffect(() => {
    void loadFromStorage();
  }, [loadFromStorage]);

  if (!initialized) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-canvas text-sm text-muted">
        正在恢复 OpenVMA 工作区…
      </div>
    );
  }

  return (
    <AppErrorBoundary>
      <RouterProvider>
        <AppRouter />
      </RouterProvider>
    </AppErrorBoundary>
  );
}
