import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { temporaryId } from "@/stores/workspaceTransforms";

export interface AppLocation {
  pathname: string;
  search: string;
  hash: string;
  state: unknown;
}

export interface NavigateOptions {
  replace?: boolean;
  state?: unknown;
}

export interface BackOptions {
  fallback: string;
}

type NavigateFunction = (to: string, options?: NavigateOptions) => boolean;
type BackFunction = (options: BackOptions) => boolean;
type NavigationBlocker = () => boolean;

interface RouterValue {
  location: AppLocation;
  navigate: NavigateFunction;
  back: BackFunction;
  canGoBack: boolean;
  previousPath: string | null;
  registerBlocker: (blocker: NavigationBlocker) => () => void;
}

interface VideoXHistoryMeta {
  sessionId: string;
  index: number;
  key: string;
  from: string | null;
}

type HistoryState = Record<string, unknown> & {
  __videox?: VideoXHistoryMeta;
};

const RouterContext = createContext<RouterValue | null>(null);
const ParamsContext = createContext<Record<string, string>>({});
const HISTORY_META_KEY = "__videox";
const SESSION_ID_KEY = "videox:navigation-session";
const SCROLL_STORAGE_PREFIX = "videox:scroll:";

function createKey(): string {
  return temporaryId("navigation");
}

function getSessionId(): string {
  const existing = window.sessionStorage.getItem(SESSION_ID_KEY);
  if (existing) return existing;
  const next = createKey();
  window.sessionStorage.setItem(SESSION_ID_KEY, next);
  return next;
}

function historyState(): HistoryState {
  const state = window.history.state;
  return state && typeof state === "object" && !Array.isArray(state)
    ? state as HistoryState
    : {};
}

function getHistoryMeta(state: unknown = window.history.state): VideoXHistoryMeta | null {
  if (!state || typeof state !== "object" || Array.isArray(state)) return null;
  const meta = (state as HistoryState)[HISTORY_META_KEY];
  return meta && typeof meta === "object" ? meta : null;
}

function withHistoryMeta(state: unknown, meta: VideoXHistoryMeta): HistoryState {
  const base = state && typeof state === "object" && !Array.isArray(state)
    ? state as Record<string, unknown>
    : state == null
      ? {}
      : { value: state };
  return { ...base, [HISTORY_META_KEY]: meta };
}

function currentPath(): string {
  return `${window.location.pathname}${window.location.search}${window.location.hash}`;
}

function currentLocation(): AppLocation {
  return {
    pathname: window.location.pathname,
    search: window.location.search,
    hash: window.location.hash,
    state: window.history.state,
  };
}

function saveScrollPosition(key?: string): void {
  if (!key) return;
  const containers = Array.from(
    document.querySelectorAll<HTMLElement>("[data-scroll-restoration]"),
  );
  const positions = Object.fromEntries(
    containers.map((element) => [element.dataset.scrollRestoration!, element.scrollTop]),
  );
  window.sessionStorage.setItem(
    `${SCROLL_STORAGE_PREFIX}${key}`,
    JSON.stringify({ window: window.scrollY, containers: positions }),
  );
}

function restoreScrollPosition(key?: string): void {
  if (!key) return;
  const raw = window.sessionStorage.getItem(`${SCROLL_STORAGE_PREFIX}${key}`);
  if (!raw) return;
  try {
    const saved = JSON.parse(raw) as { window?: number; containers?: Record<string, number> };
    window.scrollTo({ top: saved.window ?? 0, behavior: "instant" });
    for (const [name, top] of Object.entries(saved.containers ?? {})) {
      document.querySelector<HTMLElement>(`[data-scroll-restoration="${name}"]`)
        ?.scrollTo({ top, behavior: "instant" });
    }
  } catch {
    window.sessionStorage.removeItem(`${SCROLL_STORAGE_PREFIX}${key}`);
  }
}

function scrollToLocationHash(hash: string): boolean {
  if (!hash) return false;
  let id: string;
  try {
    id = decodeURIComponent(hash.slice(1));
  } catch {
    id = hash.slice(1);
  }
  if (!id) return false;
  const target = document.getElementById(id);
  if (!target) return false;
  target.scrollIntoView({ block: "start" });
  return true;
}

export function RouterProvider({ children }: { children: ReactNode }) {
  const [sessionId] = useState(getSessionId);
  const [normalizedMeta] = useState<VideoXHistoryMeta>(() => {
    const initialState = historyState();
    const initialMeta = getHistoryMeta(initialState);
    if (initialMeta?.sessionId === sessionId) return initialMeta;
    const nextMeta: VideoXHistoryMeta = {
      sessionId,
      index: 0,
      key: createKey(),
      from: null,
    };
    window.history.replaceState(withHistoryMeta(initialState, nextMeta), "", currentPath());
    return nextMeta;
  });

  const [location, setLocation] = useState<AppLocation>(currentLocation);
  const metaRef = useRef(normalizedMeta);
  const blockersRef = useRef(new Set<NavigationBlocker>());
  const bypassNextPopRef = useRef(false);

  const canLeave = useCallback(() => {
    for (const blocker of blockersRef.current) {
      if (!blocker()) return false;
    }
    return true;
  }, []);

  const registerBlocker = useCallback((blocker: NavigationBlocker) => {
    blockersRef.current.add(blocker);
    return () => {
      blockersRef.current.delete(blocker);
    };
  }, []);

  useEffect(() => {
    const syncLocation = () => {
      const nextLocation = currentLocation();
      const nextMeta = getHistoryMeta(nextLocation.state);
      const previousMeta = metaRef.current;

      if (bypassNextPopRef.current) {
        bypassNextPopRef.current = false;
        if (nextMeta) metaRef.current = nextMeta;
        setLocation(nextLocation);
        return;
      }

      if (!canLeave()) {
        if (nextMeta?.sessionId === sessionId) {
          const delta = previousMeta.index - nextMeta.index;
          if (delta !== 0) {
            bypassNextPopRef.current = true;
            window.history.go(delta);
          }
        }
        return;
      }

      saveScrollPosition(previousMeta.key);
      if (nextMeta) metaRef.current = nextMeta;
      setLocation(nextLocation);
    };
    window.addEventListener("popstate", syncLocation);
    window.addEventListener("hashchange", syncLocation);
    return () => {
      window.removeEventListener("popstate", syncLocation);
      window.removeEventListener("hashchange", syncLocation);
    };
  }, [canLeave, sessionId]);

  useLayoutEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      if (!scrollToLocationHash(location.hash)) {
        restoreScrollPosition(metaRef.current.key);
      }
    });
    return () => window.cancelAnimationFrame(frame);
  }, [location.pathname, location.search, location.hash]);

  const navigate = useCallback<NavigateFunction>((to, options = {}) => {
    if (!canLeave()) return false;
    const url = new URL(to, window.location.href);
    const next = `${url.pathname}${url.search}${url.hash}`;
    const previousMeta = metaRef.current;
    saveScrollPosition(previousMeta.key);

    const nextMeta: VideoXHistoryMeta = options.replace
      ? { ...previousMeta }
      : {
          sessionId,
          index: previousMeta.index + 1,
          key: createKey(),
          from: currentPath(),
        };
    const nextState = withHistoryMeta(options.state, nextMeta);
    if (options.replace) {
      window.history.replaceState(nextState, "", next);
    } else {
      window.history.pushState(nextState, "", next);
    }
    metaRef.current = nextMeta;
    const nextLocation = currentLocation();
    setLocation(nextLocation);
    return true;
  }, [canLeave, sessionId]);

  const back = useCallback<BackFunction>(({ fallback }) => {
    if (!canLeave()) return false;
    const meta = metaRef.current;
    if (meta.sessionId === sessionId && meta.index > 0) {
      saveScrollPosition(meta.key);
      bypassNextPopRef.current = true;
      window.history.back();
      return true;
    }
    return navigate(fallback, { replace: true });
  }, [canLeave, navigate, sessionId]);

  const value = useMemo<RouterValue>(() => {
    const meta = getHistoryMeta(location.state);
    const internalMeta = meta?.sessionId === sessionId ? meta : null;
    return {
      location,
      navigate,
      back,
      canGoBack: Boolean(internalMeta && internalMeta.index > 0),
      previousPath: internalMeta?.from ?? null,
      registerBlocker,
    };
  }, [back, location, navigate, registerBlocker, sessionId]);

  return <RouterContext.Provider value={value}>{children}</RouterContext.Provider>;
}

function useRouter() {
  const value = useContext(RouterContext);
  if (!value) throw new Error("RouterProvider 未初始化");
  return value;
}

export function useNavigate(): NavigateFunction {
  return useRouter().navigate;
}

export function useBackNavigation() {
  const { back, canGoBack, previousPath } = useRouter();
  return { back, canGoBack, previousPath };
}

export function useLocation(): AppLocation {
  return useRouter().location;
}

export function useNavigationBlocker(when: boolean, message: string): void {
  const { registerBlocker } = useRouter();
  useEffect(() => {
    if (!when) return;
    return registerBlocker(() => window.confirm(message));
  }, [message, registerBlocker, when]);
}

export function useParams<T extends Record<string, string | undefined> = Record<string, string>>() {
  return useContext(ParamsContext) as T;
}

export function useSearchParams(): [
  URLSearchParams,
  (next: URLSearchParams | string, options?: NavigateOptions) => void,
] {
  const location = useLocation();
  const navigate = useNavigate();
  const params = useMemo(() => new URLSearchParams(location.search), [location.search]);
  const setParams = useCallback(
    (next: URLSearchParams | string, options?: NavigateOptions) => {
      const value = typeof next === "string" ? next : next.toString();
      navigate(
        `${location.pathname}${value ? `?${value.replace(/^\?/, "")}` : ""}${location.hash}`,
        options,
      );
    },
    [location.hash, location.pathname, navigate],
  );
  return [params, setParams];
}

export function RouteParams({ params, children }: { params: Record<string, string>; children: ReactNode }) {
  return <ParamsContext.Provider value={params}>{children}</ParamsContext.Provider>;
}

export function Navigate({ to, replace = false, state }: { to: string; replace?: boolean; state?: unknown }) {
  const navigate = useNavigate();
  useEffect(() => {
    navigate(to, { replace, state });
  }, [navigate, replace, state, to]);
  return null;
}

export function matchPath(pattern: string, pathname: string): Record<string, string> | null {
  const patternParts = pattern.split("/").filter(Boolean);
  const pathParts = pathname.split("/").filter(Boolean);
  if (patternParts.length !== pathParts.length) return null;

  const params: Record<string, string> = {};
  for (let index = 0; index < patternParts.length; index += 1) {
    const expected = patternParts[index];
    const actual = pathParts[index];
    if (expected.startsWith(":")) {
      try {
        params[expected.slice(1)] = decodeURIComponent(actual);
      } catch {
        return null;
      }
    } else if (expected !== actual) {
      return null;
    }
  }
  return params;
}
