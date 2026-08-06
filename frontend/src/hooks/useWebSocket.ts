// ──────────────────────────────────────────────
// OpenVMA - WebSocket Hook
// 连接 /api/ws/jobs，发送 token 认证，接收任务状态推送，自动重连
// ──────────────────────────────────────────────

import { useEffect, useRef, useState, useCallback } from "react";
import { getAccessToken } from "@/api/client";
import { useJobStore } from "@/stores/jobStore";
import type { Job } from "@/types/models";

type WSMessage =
  | { type: "job_update"; job: Job }
  | { type: "job_progress"; jobId: string; progress: number; stage: string; stageIndex: number }
  | { type: "job_completed"; jobId: string; job: Job }
  | { type: "auth_ok" }
  | { type: "auth_failed"; detail: string }
  | { type: "ping" };

interface UseWebSocketOptions {
  /** 是否启用连接（默认在已认证时自动连接） */
  enabled?: boolean;
  /** 重连间隔（毫秒），默认 3000 */
  reconnectInterval?: number;
  /** 最大重连次数，默认 10 */
  maxRetries?: number;
}

interface UseWebSocketReturn {
  connected: boolean;
  error: string | null;
  /** 手动重连 */
  reconnect: () => void;
}

/**
 * WebSocket hook：连接任务推送通道
 *
 * - 连接 /api/ws/jobs（通过 Vite proxy 转发到后端）
 * - 连接成功后发送 { type: "auth", token: "..." } 认证
 * - 接收 job_update / job_progress / job_completed 消息，自动更新 jobStore
 * - 断线自动重连，指数退避
 */
export function useWebSocket(options?: UseWebSocketOptions): UseWebSocketReturn {
  const { enabled = true, reconnectInterval = 3000, maxRetries = 10 } = options ?? {};

  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const retryCount = useRef(0);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const intentionallyClosed = useRef(false);
  const connectRef = useRef<() => void>(() => undefined);

  const upsertJob = useJobStore((s) => s.upsertJob);
  const patchJob = useJobStore((s) => s.patchJob);

  const handleMessage = useCallback(
    (event: MessageEvent) => {
      try {
        const msg: WSMessage = JSON.parse(event.data);
        switch (msg.type) {
          case "job_update": {
            upsertJob(msg.job);
            break;
          }
          case "job_completed": {
            upsertJob(msg.job);
            break;
          }
          case "job_progress": {
            patchJob(msg.jobId, {
              progress: msg.progress,
              stage: msg.stage,
              stageIndex: msg.stageIndex,
            });
            break;
          }
          case "auth_failed": {
            setError(msg.detail || "WebSocket 认证失败");
            break;
          }
          case "auth_ok":
          case "ping":
            break;
        }
      } catch {
        // 忽略无法解析的消息
      }
    },
    [upsertJob, patchJob],
  );

  const connect = useCallback(() => {
    if (intentionallyClosed.current) return;

    const token = getAccessToken();
    if (!token) {
      setError("未检测到登录令牌，跳过 WebSocket 连接");
      return;
    }

    // 关闭旧连接
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.close();
      wsRef.current = null;
    }

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/api/ws/jobs`;
    const socket = new WebSocket(wsUrl);
    wsRef.current = socket;

    socket.onopen = () => {
      setConnected(true);
      setError(null);
      retryCount.current = 0;
      // 发送 token 认证
      socket.send(JSON.stringify({ type: "auth", token }));
    };

    socket.onmessage = handleMessage;

    socket.onerror = () => {
      setError("WebSocket 连接错误");
    };

    socket.onclose = () => {
      setConnected(false);
      wsRef.current = null;

      if (intentionallyClosed.current) return;

      // 自动重连（指数退避）
      if (retryCount.current < maxRetries) {
        const delay = reconnectInterval * Math.pow(1.5, retryCount.current);
        retryCount.current += 1;
        reconnectTimer.current = setTimeout(() => {
          connectRef.current();
        }, delay);
      } else {
        setError("WebSocket 重连次数已达上限，请刷新页面重试");
      }
    };
  }, [handleMessage, reconnectInterval, maxRetries]);

  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  const reconnect = useCallback(() => {
    retryCount.current = 0;
    intentionallyClosed.current = false;
    connect();
  }, [connect]);

  useEffect(() => {
    if (!enabled) return;

    intentionallyClosed.current = false;
    connect();

    return () => {
      intentionallyClosed.current = true;
      if (reconnectTimer.current) {
        clearTimeout(reconnectTimer.current);
        reconnectTimer.current = null;
      }
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
        wsRef.current = null;
      }
      setConnected(false);
    };
  }, [enabled, connect]);

  return { connected, error, reconnect };
}
