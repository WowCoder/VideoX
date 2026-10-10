import type { LoginRequest, RegisterRequest } from "../types/models";

export interface EmailAuthFields {
  email: string;
  name: string;
  password: string;
}

/** Validate form input before calling the existing store's email actions. */
export async function authenticateWithEmail<T>(
  mode: "login" | "register",
  fields: EmailAuthFields,
  actions: {
    login: (request: LoginRequest) => Promise<T>;
    register: (request: RegisterRequest) => Promise<T>;
  },
): Promise<T> {
  const email = fields.email.trim();
  const name = fields.name.trim();
  const password = fields.password;
  // The API's EmailStr remains authoritative for full address validation.
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) throw new Error("请输入有效的邮箱地址");
  if (!password) throw new Error("请输入密码");
  if (mode === "login") return actions.login({ email, password });
  const nameLength = Array.from(name).length;
  const passwordLength = Array.from(password).length;
  if (nameLength < 1 || nameLength > 100) throw new Error("姓名须为 1–100 个字符");
  if (passwordLength < 6 || passwordLength > 128) throw new Error("密码须为 6–128 个字符");
  return actions.register({ email, name, password });
}
