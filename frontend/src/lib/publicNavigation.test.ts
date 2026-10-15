import assert from "node:assert/strict";
import test from "node:test";
import {
  decodeWechatNavigationState,
  encodeWechatNavigationState,
  getPostAuthStartAction,
  postAuthStartAction,
} from "./publicNavigation.ts";

test("官网创作入口会把具体开始方式保留到认证后", () => {
  for (const method of ["ai-script", "write-script", "upload-assets"] as const) {
    const state = postAuthStartAction(method);
    assert.deepEqual(getPostAuthStartAction(state), {
      kind: "start-project",
      method,
    });
  }
});

test("未知的认证后动作不会触发项目创建", () => {
  assert.equal(getPostAuthStartAction(null), null);
  assert.equal(getPostAuthStartAction({ postAuthAction: { kind: "start-project", method: "unknown" } }), null);
  assert.equal(getPostAuthStartAction({ postAuthAction: { kind: "other", method: "ai-script" } }), null);
});

test("微信扫码 state 可以往返携带创作意图", () => {
  const action = { kind: "start-project", method: "upload-assets" } as const;
  assert.equal(encodeWechatNavigationState(action), "start-project:upload-assets");
  assert.deepEqual(decodeWechatNavigationState("start-project:upload-assets"), action);
  assert.equal(decodeWechatNavigationState("videox"), null);
});
