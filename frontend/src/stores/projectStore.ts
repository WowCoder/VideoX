// ──────────────────────────────────────────────
// OpenVMA - 项目状态管理（Zustand）
// ──────────────────────────────────────────────

import { create } from "zustand";
import * as projectApi from "@/api/projects";
import type { Project } from "@/types/models";
import type { ProjectCreateInput, ProjectUpdateInput, ProjectListParams } from "@/api/projects";

interface ProjectState {
  projects: Project[];
  currentProjectId: string | null;
  loading: boolean;
  error: string | null;

  fetchProjects: (params?: ProjectListParams) => Promise<Project[]>;
  createProject: (data: ProjectCreateInput) => Promise<Project>;
  setCurrentProject: (id: string | null) => void;
  updateProject: (id: string, data: ProjectUpdateInput) => Promise<Project>;
  deleteProject: (id: string) => Promise<void>;
  getProjectById: (id: string) => Project | undefined;
  clearError: () => void;
}

export const useProjectStore = create<ProjectState>((set, get) => ({
  projects: [],
  currentProjectId: null,
  loading: false,
  error: null,

  fetchProjects: async (params?: ProjectListParams) => {
    set({ loading: true, error: null });
    try {
      const res = await projectApi.list(params);
      const projects = res.items;
      set({ projects, loading: false });
      return projects;
    } catch (err) {
      const message = err instanceof Error ? err.message : "获取项目列表失败";
      set({ loading: false, error: message });
      throw err;
    }
  },

  createProject: async (data: ProjectCreateInput) => {
    set({ loading: true, error: null });
    try {
      const project = await projectApi.create(data);
      set((state) => ({
        projects: [project, ...state.projects],
        currentProjectId: project.id,
        loading: false,
      }));
      return project;
    } catch (err) {
      const message = err instanceof Error ? err.message : "创建项目失败";
      set({ loading: false, error: message });
      throw err;
    }
  },

  setCurrentProject: (id: string | null) => {
    set({ currentProjectId: id });
  },

  updateProject: async (id: string, data: ProjectUpdateInput) => {
    set({ loading: true, error: null });
    try {
      const updated = await projectApi.update(id, data);
      set((state) => ({
        projects: state.projects.map((p) => (p.id === id ? updated : p)),
        loading: false,
      }));
      return updated;
    } catch (err) {
      const message = err instanceof Error ? err.message : "更新项目失败";
      set({ loading: false, error: message });
      throw err;
    }
  },

  deleteProject: async (id: string) => {
    set({ loading: true, error: null });
    try {
      await projectApi.remove(id);
      set((state) => ({
        projects: state.projects.filter((p) => p.id !== id),
        currentProjectId:
          state.currentProjectId === id ? null : state.currentProjectId,
        loading: false,
      }));
    } catch (err) {
      const message = err instanceof Error ? err.message : "删除项目失败";
      set({ loading: false, error: message });
      throw err;
    }
  },

  getProjectById: (id: string) => {
    return get().projects.find((p) => p.id === id);
  },

  clearError: () => set({ error: null }),
}));
