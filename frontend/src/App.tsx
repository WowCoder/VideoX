import { useEffect } from "react";
import { RouterProvider } from "@/router";
import AppRouter from "@/routes";
import { useAuthStore } from "@/stores/authStore";
import { AppErrorBoundary } from "@/components/AppErrorBoundary";
import * as activityApi from "@/api/activity";

const ACTIVITY_HEARTBEAT_INTERVAL_MS = 15 * 60 * 1000;
const RECENT_INTERACTION_WINDOW_MS = 5 * 60 * 1000;

export default function App() {
  const initialized = useAuthStore((s) => s.initialized);
  const loadFromStorage = useAuthStore((s) => s.loadFromStorage);
  const userId = useAuthStore((s) => s.user?.id);

  useEffect(() => {
    void loadFromStorage();
  }, [loadFromStorage]);

  useEffect(() => {
    if (!initialized || !userId) return;

    let lastSentAt = 0;
    let lastInteractionAt = Date.now();
    const sendHeartbeat = (force = false) => {
      const now = Date.now();
      if (document.visibilityState !== "visible") return;
      if (!force && now - lastInteractionAt > RECENT_INTERACTION_WINDOW_MS) return;
      if (now - lastSentAt < ACTIVITY_HEARTBEAT_INTERVAL_MS) return;
      lastSentAt = now;
      void activityApi.heartbeat().catch(() => {
        // 活跃统计不能影响用户正常使用；下次真实交互时会继续尝试。
        lastSentAt = 0;
      });
    };
    const markInteraction = () => {
      lastInteractionAt = Date.now();
      sendHeartbeat();
    };
    const handleVisibility = () => {
      if (document.visibilityState === "visible") {
        lastInteractionAt = Date.now();
        sendHeartbeat(true);
      }
    };

    sendHeartbeat(true);
    window.addEventListener("pointerdown", markInteraction, { passive: true });
    window.addEventListener("keydown", markInteraction);
    window.addEventListener("focus", handleVisibility);
    document.addEventListener("visibilitychange", handleVisibility);
    return () => {
      window.removeEventListener("pointerdown", markInteraction);
      window.removeEventListener("keydown", markInteraction);
      window.removeEventListener("focus", handleVisibility);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [initialized, userId]);

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
