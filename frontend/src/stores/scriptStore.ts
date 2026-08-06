// ──────────────────────────────────────────────
// OpenVMA - 脚本状态管理（Zustand）
// ──────────────────────────────────────────────

import { create } from "zustand";
import * as scriptApi from "@/api/scripts";
import type { Script, ScriptUnit, VisualConfig } from "@/types/models";
import type {
  ScriptCreateInput,
  ScriptUpdateInput,
  ScriptListParams,
} from "@/api/scripts";

/** 当前脚本的完整结构（含分镜单元） */
type CurrentScript = (Script & { units: ScriptUnit[] }) | null;

interface ScriptState {
  scripts: Script[];
  currentScriptId: string | null;
  currentScript: CurrentScript;
  loading: boolean;
  error: string | null;

  fetchScripts: (params?: ScriptListParams) => Promise<Script[]>;
  /** 设置当前脚本 ID（不加载详情） */
  setCurrentScriptId: (id: string | null) => void;
  /** 加载脚本详情（含 units），同时设置 currentScript */
  fetchScript: (id: string) => Promise<CurrentScript>;
  /** 直接设置当前脚本（用于从 React Query 数据初始化） */
  setCurrentScript: (script: CurrentScript) => void;
  createScript: (data: ScriptCreateInput) => Promise<Script>;
  /** 保存脚本：更新元信息 + 批量保存分镜单元 */
  saveScript: (
    id: string,
    data: { meta?: ScriptUpdateInput; units?: ScriptUnit[] },
  ) => Promise<void>;
  /** 生成 AI 初剪项目 */
  createRoughCut: (
    id: string,
    options?: { title?: string; visualConfig?: VisualConfig },
  ) => Promise<scriptApi.RoughCutResult>;
  deleteScript: (id: string) => Promise<void>;
  getScriptById: (id: string) => Script | undefined;
  /** 更新当前脚本的本地分镜草稿（不立即持久化） */
  updateCurrentUnits: (units: ScriptUnit[]) => void;
  clearError: () => void;
}

export const useScriptStore = create<ScriptState>((set, get) => ({
  scripts: [],
  currentScriptId: null,
  currentScript: null,
  loading: false,
  error: null,

  fetchScripts: async (params?: ScriptListParams) => {
    set({ loading: true, error: null });
    try {
      const res = await scriptApi.list(params);
      const scripts = res.items;
      set({ scripts, loading: false });
      return scripts;
    } catch (err) {
      const message = err instanceof Error ? err.message : "获取脚本列表失败";
      set({ loading: false, error: message });
      throw err;
    }
  },

  setCurrentScriptId: (id: string | null) => {
    set({ currentScriptId: id });
  },

  setCurrentScript: (script: CurrentScript) => {
    set({
      currentScript: script,
      currentScriptId: script?.id ?? null,
    });
  },

  fetchScript: async (id: string) => {
    set({ loading: true, error: null });
    try {
      const detail = await scriptApi.get(id);
      const current: CurrentScript = { ...detail };
      set((state) => ({
        currentScriptId: id,
        currentScript: current,
        scripts: state.scripts.some((s) => s.id === id)
          ? state.scripts.map((s) => (s.id === id ? { ...s, ...detail } : s))
          : [...state.scripts, detail],
        loading: false,
      }));
      return current;
    } catch (err) {
      const message = err instanceof Error ? err.message : "加载脚本详情失败";
      set({ loading: false, error: message });
      throw err;
    }
  },

  createScript: async (data: ScriptCreateInput) => {
    set({ loading: true, error: null });
    try {
      const script = await scriptApi.create(data);
      set((state) => ({
        scripts: [script, ...state.scripts],
        currentScriptId: script.id,
        loading: false,
      }));
      return script;
    } catch (err) {
      const message = err instanceof Error ? err.message : "创建脚本失败";
      set({ loading: false, error: message });
      throw err;
    }
  },

  saveScript: async (
    id: string,
    data: { meta?: ScriptUpdateInput; units?: ScriptUnit[] },
  ) => {
    set({ loading: true, error: null });
    try {
      // 并行更新元信息和分镜单元
      const promises: Promise<unknown>[] = [];
      if (data.meta) {
        promises.push(scriptApi.update(id, data.meta));
      }
      if (data.units) {
        promises.push(scriptApi.batchUpdateUnits(id, data.units));
      }
      const results = await Promise.all(promises);

      // 从结果中提取更新后的数据
      let updatedScript: Script | undefined;
      let updatedUnits: ScriptUnit[] | undefined;
      for (const res of results) {
        if (res && typeof res === "object" && "units" in res) {
          updatedUnits = (res as { units: ScriptUnit[] }).units;
        } else if (res && typeof res === "object" && "id" in res) {
          updatedScript = res as Script;
        }
      }

      set((state) => ({
        scripts: updatedScript
          ? state.scripts.map((s) => (s.id === id ? { ...s, ...updatedScript! } : s))
          : state.scripts,
        currentScript:
          state.currentScriptId === id
            ? {
                ...(state.currentScript as Script & { units: ScriptUnit[] }),
                ...(updatedScript ?? {}),
                units: updatedUnits ?? state.currentScript?.units ?? [],
              }
            : state.currentScript,
        loading: false,
      }));
    } catch (err) {
      const message = err instanceof Error ? err.message : "保存脚本失败";
      set({ loading: false, error: message });
      throw err;
    }
  },

  createRoughCut: async (
    id: string,
    options?: { title?: string; visualConfig?: VisualConfig },
  ) => {
    set({ loading: true, error: null });
    try {
      const result = await scriptApi.createRoughCut(id, options);
      set({ loading: false });
      return result;
    } catch (err) {
      const message = err instanceof Error ? err.message : "生成初剪失败";
      set({ loading: false, error: message });
      throw err;
    }
  },

  deleteScript: async (id: string) => {
    set({ loading: true, error: null });
    try {
      await scriptApi.remove(id);
      set((state) => ({
        scripts: state.scripts.filter((s) => s.id !== id),
        currentScriptId:
          state.currentScriptId === id ? null : state.currentScriptId,
        currentScript:
          state.currentScriptId === id ? null : state.currentScript,
        loading: false,
      }));
    } catch (err) {
      const message = err instanceof Error ? err.message : "删除脚本失败";
      set({ loading: false, error: message });
      throw err;
    }
  },

  getScriptById: (id: string) => {
    return get().scripts.find((s) => s.id === id);
  },

  updateCurrentUnits: (units: ScriptUnit[]) => {
    set((state) => ({
      currentScript: state.currentScript
        ? { ...state.currentScript, units }
        : state.currentScript,
    }));
  },

  clearError: () => set({ error: null }),
}));
