import assert from "node:assert/strict";
import test from "node:test";
import { authenticateWithEmail } from "./emailAuth.ts";

const fields = { email: " reader@example.com ", name: " Reader ", password: " pass word " };

function authBoundary() {
  const requests: unknown[] = [];
  return {
    requests,
    login: async (data: unknown) => { requests.push({ mode: "login", data }); return { name: "Reader" }; },
    register: async (data: unknown) => { requests.push({ mode: "register", data }); return { name: "Reader" }; },
  };
}

test("email registration submits normalized identity and preserves password whitespace", async () => {
  const boundary = authBoundary();
  assert.deepEqual(await authenticateWithEmail("register", fields, boundary), { name: "Reader" });
  assert.deepEqual(boundary.requests, [{ mode: "register", data: { email: "reader@example.com", name: "Reader", password: " pass word " } }]);
});

test("email login excludes registration-only fields and accepts an existing short password", async () => {
  const boundary = authBoundary();
  await authenticateWithEmail("login", { ...fields, name: "", password: "short" }, boundary);
  assert.deepEqual(boundary.requests, [{ mode: "login", data: { email: "reader@example.com", password: "short" } }]);
});

test("invalid email and empty password do not reach authentication", async () => {
  for (const invalid of [{ ...fields, email: "invalid" }, { ...fields, password: "" }]) {
    const boundary = authBoundary();
    await assert.rejects(authenticateWithEmail("login", invalid, boundary));
    assert.deepEqual(boundary.requests, []);
  }
});

test("registration rejects names and passwords outside backend schema lengths", async () => {
  for (const invalid of [
    { ...fields, name: " " }, { ...fields, name: "x".repeat(101) },
    { ...fields, password: "12345" }, { ...fields, password: "x".repeat(129) },
  ]) {
    const boundary = authBoundary();
    await assert.rejects(authenticateWithEmail("register", invalid, boundary));
    assert.deepEqual(boundary.requests, []);
  }
});

test("registration accepts the schema boundaries including Unicode character lengths", async () => {
  for (const valid of [
    { ...fields, name: "R", password: "123456" },
    { ...fields, name: "😀".repeat(100), password: "😀".repeat(128) },
  ]) {
    const boundary = authBoundary();
    await authenticateWithEmail("register", valid, boundary);
    assert.equal(boundary.requests.length, 1);
  }
});

test("server authentication errors propagate unchanged for visible form feedback", async () => {
  const serverError = new Error("邮箱已被注册");
  const boundary = { login: async () => { throw serverError; }, register: async () => { throw serverError; } };
  for (const mode of ["login", "register"] as const) {
    await assert.rejects(authenticateWithEmail(mode, fields, boundary), (error) => error === serverError);
  }
});
