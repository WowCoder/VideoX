import type { ProjectStartMethod } from "@/stores/uiStore";

export type PublicStartMethod = Exclude<ProjectStartMethod, "blank">;

export interface PostAuthStartAction {
  kind: "start-project";
  method: PublicStartMethod;
}

export interface PublicNavigationState {
  postAuthAction?: PostAuthStartAction;
}

const validStartMethods = new Set<PublicStartMethod>([
  "ai-script",
  "write-script",
  "upload-assets",
]);

export function postAuthStartAction(method: PublicStartMethod): PublicNavigationState {
  return { postAuthAction: { kind: "start-project", method } };
}

export function getPostAuthStartAction(state: unknown): PostAuthStartAction | null {
  if (!state || typeof state !== "object" || Array.isArray(state)) return null;
  const action = (state as PublicNavigationState).postAuthAction;
  if (!action || action.kind !== "start-project" || !validStartMethods.has(action.method)) return null;
  return action;
}

export function encodeWechatNavigationState(action: PostAuthStartAction | null): string {
  return action ? `start-project:${action.method}` : "openvma";
}

export function decodeWechatNavigationState(value: string | null): PostAuthStartAction | null {
  if (!value?.startsWith("start-project:")) return null;
  const method = value.slice("start-project:".length) as PublicStartMethod;
  return validStartMethods.has(method) ? { kind: "start-project", method } : null;
}
