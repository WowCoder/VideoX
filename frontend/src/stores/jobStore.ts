// ──────────────────────────────────────────────
// VideoX - 异步任务状态管理（Zustand）
// WebSocket 实时推送逻辑见 hooks/useWebSocket
// ──────────────────────────────────────────────

import { create } from "zustand";
import * as jobApi from "@/api/jobs";
import type { Job } from "@/types/models";
import type { JobListParams } from "@/api/jobs";

interface JobState {
  jobs: Job[];
  loading: boolean;
  error: string | null;

  fetchJobs: (params?: JobListParams) => Promise<Job[]>;
  getJobById: (id: string) => Job | undefined;
  retryJob: (id: string) => Promise<Job>;
  cancelJob: (id: string) => Promise<Job>;
  pauseJob: (id: string) => Promise<Job>;
  resumeJob: (id: string) => Promise<Job>;
  /** 更新或插入单个 job（供 WebSocket 推送调用） */
  upsertJob: (job: Job) => void;
  /** 局部更新 job 字段（供 WebSocket 进度推送调用） */
  patchJob: (jobId: string, patch: Partial<Job>) => void;

  clearError: () => void;
}

export const useJobStore = create<JobState>((set, get) => ({
  jobs: [],
  loading: false,
  error: null,

  fetchJobs: async (params?: JobListParams) => {
    set({ loading: true, error: null });
    try {
      const res = await jobApi.list(params);
      const jobs = res.items;
      set({ jobs, loading: false });
      return jobs;
    } catch (err) {
      const message = err instanceof Error ? err.message : "获取任务列表失败";
      set({ loading: false, error: message });
      throw err;
    }
  },

  getJobById: (id: string) => {
    return get().jobs.find((j) => j.id === id);
  },

  retryJob: async (id: string) => {
    set({ loading: true, error: null });
    try {
      const job = await jobApi.retry(id);
      set((state) => ({
        jobs: state.jobs.map((j) => (j.id === id ? job : j)),
        loading: false,
      }));
      return job;
    } catch (err) {
      const message = err instanceof Error ? err.message : "重试任务失败";
      set({ loading: false, error: message });
      throw err;
    }
  },

  cancelJob: async (id: string) => {
    try {
      const job = await jobApi.cancel(id);
      set((state) => ({ jobs: state.jobs.map((item) => (item.id === id ? job : item)) }));
      return job;
    } catch (err) {
      const message = err instanceof Error ? err.message : "取消任务失败";
      set({ error: message });
      throw err;
    }
  },

  pauseJob: async (id: string) => {
    try {
      const job = await jobApi.pause(id);
      set((state) => ({
        jobs: state.jobs.map((j) => (j.id === id ? job : j)),
      }));
      return job;
    } catch (err) {
      const message = err instanceof Error ? err.message : "暂停任务失败";
      set({ error: message });
      throw err;
    }
  },

  resumeJob: async (id: string) => {
    try {
      const job = await jobApi.resume(id);
      set((state) => ({
        jobs: state.jobs.map((j) => (j.id === id ? job : j)),
      }));
      return job;
    } catch (err) {
      const message = err instanceof Error ? err.message : "恢复任务失败";
      set({ error: message });
      throw err;
    }
  },

  upsertJob: (job: Job) => {
    set((state) => {
      const exists = state.jobs.some((j) => j.id === job.id);
      return {
        jobs: exists
          ? state.jobs.map((j) => (j.id === job.id ? job : j))
          : [job, ...state.jobs],
      };
    });
  },

  patchJob: (jobId: string, patch: Partial<Job>) => {
    set((state) => ({
      jobs: state.jobs.map((j) => (j.id === jobId ? { ...j, ...patch } : j)),
    }));
  },

  clearError: () => set({ error: null }),
}));
