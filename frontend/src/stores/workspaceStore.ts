import { create } from "zustand";
import { HttpClientError } from "@/api/client";
import * as projectApi from "@/api/projects";
import type { GlobalScopeLayers, Scene, Shot, Workspace } from "@/api/projects";
import {
  moveScene as moveSceneTransform,
  removeShotAsset as removeShotAssetTransform,
  splitShot as splitShotTransform,
  synchronizeTimeline,
  temporaryId,
} from "@/stores/workspaceTransforms";

export type SaveState = "idle" | "dirty" | "saving" | "saved" | "error" | "conflict";

interface UndoState {
  token: string;
  expiresAt: string;
  label: string;
}

interface WorkspaceState {
  workspace: Workspace | null;
  loading: boolean;
  saveState: SaveState;
  saveError: string | null;
  selectedSceneId: string | null;
  selectedShotId: string | null;
  undo: UndoState | null;
  load: (projectId: string) => Promise<Workspace>;
  hydrate: (workspace: Workspace) => void;
  updateProject: (patch: Partial<Workspace["project"]>) => void;
  updateDocumentSettings: (patch: Partial<Workspace["document"]["settings"]>) => void;
  applyGlobalColorGrade: (colorGrade: Record<string, unknown>, clearShotOverrides: boolean) => void;
  updateGlobalScope: (scope: "film" | "scene", sceneId: string | undefined, patch: Partial<GlobalScopeLayers>) => void;
  selectScene: (sceneId: string | null) => void;
  selectShot: (shotId: string | null) => void;
  updateScene: (sceneId: string, patch: Partial<Scene>) => void;
  moveScene: (sceneId: string, direction: -1 | 1) => void;
  updateShot: (sceneId: string, shotId: string, patch: Partial<Shot>) => void;
  moveShot: (sceneId: string, shotId: string, direction: -1 | 1) => void;
  splitShot: (sceneId: string, shotId: string, offsetMs: number) => void;
  removeShotAsset: (sceneId: string, shotId: string) => void;
  duplicateShot: (sceneId: string, shotId: string) => void;
  restoreDerivedSubtitle: (sceneId: string, shotId: string) => void;
  addScene: () => void;
  addShot: (sceneId: string) => void;
  save: (reason?: "autosave" | "manual_save" | "before_ai_operation") => Promise<Workspace | null>;
  deleteScene: (sceneId: string) => Promise<void>;
  deleteShot: (shotId: string) => Promise<void>;
  undoDelete: () => Promise<void>;
  reloadServer: () => Promise<void>;
  clear: () => void;
}

let autosaveTimer: number | undefined;
let undoTimer: number | undefined;
let editVersion = 0;
let savePromise: Promise<Workspace | null> | null = null;

function scheduleAutosave(get: () => WorkspaceState) {
  window.clearTimeout(autosaveTimer);
  autosaveTimer = window.setTimeout(() => void get().save("autosave").catch(() => undefined), 1000);
}

function newShot(index: number, narration: string): Shot {
  return {
    id: temporaryId("new-shot"),
    index,
    description: "",
    status: "editing",
    sourceStartMs: 0,
    sourceEndMs: 8000,
    durationMs: 8000,
    locked: false,
    transform: {},
    adjust: {},
    audioSettings: {},
    subtitleSettings: {},
    transition: {},
    motion: {},
    subtitleText: narration,
    subtitleOverridden: false,
    subtitleSourceRevision: 0,
    subtitleOutdated: false,
    notes: "",
    revision: 0,
    candidates: [],
    mediaVersions: [],
  };
}

function persistedId(id?: string): string | undefined {
  return id?.startsWith("new-") ? undefined : id;
}

function synchronizeWorkspace(workspace: Workspace): Workspace {
  return { ...workspace, document: synchronizeTimeline(workspace.document) };
}

function prepareForSave(workspace: Workspace): Workspace {
  return synchronizeWorkspace({
    ...workspace,
    document: {
      ...workspace.document,
      storyboard: {
        scenes: workspace.document.storyboard.scenes.map((scene, sceneIndex) => ({
          ...scene,
          id: persistedId(scene.id),
          index: sceneIndex,
          shots: scene.shots.map((shot, shotIndex) => ({
            ...shot,
            id: persistedId(shot.id),
            index: shotIndex,
          })),
        })),
      },
    },
  });
}

function mergeAfterConcurrentEdit(server: Workspace, local: Workspace): Workspace {
  const serverScenes = server.document.storyboard.scenes;
  return {
    ...server,
    project: { ...server.project, ...local.project, id: server.project.id },
    document: {
      ...server.document,
      ...local.document,
      id: server.document.id,
      revision: server.document.revision,
      settings: { ...server.document.settings, ...local.document.settings },
      storyboard: {
        scenes: local.document.storyboard.scenes.map((localScene, sceneIndex) => {
          const serverScene = serverScenes.find((item) => item.id === persistedId(localScene.id))
            ?? serverScenes[sceneIndex];
          if (!serverScene) return localScene;
          return {
            ...serverScene,
            ...localScene,
            id: serverScene.id,
            revision: serverScene.revision,
            shots: localScene.shots.map((localShot, shotIndex) => {
              const serverShot = serverScene.shots.find((item) => item.id === persistedId(localShot.id))
                ?? serverScene.shots[shotIndex];
              return serverShot
                ? { ...serverShot, ...localShot, id: serverShot.id, revision: serverShot.revision }
                : localShot;
            }),
          };
        }),
      },
    },
  };
}

function remapSelection(
  previous: Workspace,
  next: Workspace,
  selectedSceneId: string | null,
  selectedShotId: string | null,
) {
  const previousScenes = previous.document.storyboard.scenes;
  const nextScenes = next.document.storyboard.scenes;
  const previousSceneIndex = Math.max(0, previousScenes.findIndex((scene) => scene.id === selectedSceneId));
  const previousScene = previousScenes[previousSceneIndex];
  const previousShotIndex = Math.max(0, previousScene?.shots.findIndex((shot) => shot.id === selectedShotId) ?? 0);
  const nextScene = nextScenes.find((scene) => scene.id === persistedId(selectedSceneId ?? undefined))
    ?? nextScenes[previousSceneIndex]
    ?? nextScenes[0];
  const nextShot = nextScene?.shots.find((shot) => shot.id === persistedId(selectedShotId ?? undefined))
    ?? nextScene?.shots[previousShotIndex]
    ?? nextScene?.shots[0];
  return { selectedSceneId: nextScene?.id ?? null, selectedShotId: nextShot?.id ?? null };
}

function dirty(
  set: (partial: Partial<WorkspaceState> | ((state: WorkspaceState) => Partial<WorkspaceState>)) => void,
  get: () => WorkspaceState,
  updater: (workspace: Workspace) => Workspace,
) {
  editVersion += 1;
  set((state) => state.workspace
    ? {
        workspace: synchronizeWorkspace(updater(state.workspace)),
        saveState: state.saveState === "conflict" ? "conflict" : "dirty",
        saveError: state.saveState === "conflict" ? state.saveError : null,
      }
    : {});
  if (get().workspace?.project.id !== "__preview__" && get().saveState !== "conflict") scheduleAutosave(get);
}

export const useWorkspaceStore = create<WorkspaceState>((set, get) => ({
  workspace: null,
  loading: false,
  saveState: "idle",
  saveError: null,
  selectedSceneId: null,
  selectedShotId: null,
  undo: null,

  load: async (projectId) => {
    window.clearTimeout(autosaveTimer);
    window.clearTimeout(undoTimer);
    set({ loading: true, saveError: null, undo: null });
    try {
      const workspace = synchronizeWorkspace(await projectApi.getWorkspace(projectId));
      editVersion = 0;
      set({
        workspace,
        loading: false,
        saveState: "saved",
        selectedSceneId: workspace.document.storyboard.scenes[0]?.id ?? null,
        selectedShotId: workspace.document.storyboard.scenes[0]?.shots[0]?.id ?? null,
      });
      return workspace;
    } catch (error) {
      set({ loading: false, saveState: "error", saveError: error instanceof Error ? error.message : "项目加载失败" });
      throw error;
    }
  },

  hydrate: (workspace) => {
    workspace = synchronizeWorkspace(workspace);
    window.clearTimeout(autosaveTimer);
    editVersion = 0;
    set({
      workspace,
      loading: false,
      saveState: "saved",
      saveError: null,
      undo: null,
      selectedSceneId: workspace.document.storyboard.scenes[0]?.id ?? null,
      selectedShotId: workspace.document.storyboard.scenes[0]?.shots[0]?.id ?? null,
    });
  },

  updateProject: (patch) => dirty(set, get, (workspace) => ({
    ...workspace,
    project: { ...workspace.project, ...patch },
  })),

  updateDocumentSettings: (patch) => dirty(set, get, (workspace) => ({
    ...workspace,
    document: {
      ...workspace.document,
      settings: { ...workspace.document.settings, ...patch },
    },
  })),

  applyGlobalColorGrade: (colorGrade, clearShotOverrides) => dirty(set, get, (workspace) => ({
    ...workspace,
    document: {
      ...workspace.document,
      settings: {
        ...workspace.document.settings,
        visualSettings: {
          ...workspace.document.settings.visualSettings,
          colorGrade,
        },
      },
      storyboard: clearShotOverrides
        ? {
            scenes: workspace.document.storyboard.scenes.map((scene) => ({
              ...scene,
              shots: scene.shots.map((shot) => ({ ...shot, adjust: { mode: "inherit" } })),
            })),
          }
        : workspace.document.storyboard,
    },
  })),

  updateGlobalScope: (scope, sceneId, patch) => dirty(set, get, (workspace) => {
    const current = scope === "film"
      ? workspace.document.globalScopes.film
      : sceneId ? workspace.document.globalScopes.scenes[sceneId] ?? {} : {};
    const nextScope = { ...current, ...patch };
    return {
      ...workspace,
      document: {
        ...workspace.document,
        globalScopes: scope === "film"
          ? { ...workspace.document.globalScopes, film: nextScope }
          : sceneId
            ? {
                ...workspace.document.globalScopes,
                scenes: { ...workspace.document.globalScopes.scenes, [sceneId]: nextScope },
              }
            : workspace.document.globalScopes,
      },
    };
  }),

  selectScene: (sceneId) => {
    const scene = get().workspace?.document.storyboard.scenes.find((item) => item.id === sceneId);
    set({ selectedSceneId: sceneId, selectedShotId: scene?.shots[0]?.id ?? null });
  },
  selectShot: (shotId) => {
    const scene = get().workspace?.document.storyboard.scenes.find((item) => (
      item.shots.some((shot) => shot.id === shotId)
    ));
    set({
      selectedSceneId: scene?.id ?? get().selectedSceneId,
      selectedShotId: shotId,
    });
  },

  updateScene: (sceneId, patch) => dirty(set, get, (workspace) => ({
    ...workspace,
    document: {
      ...workspace.document,
      storyboard: { scenes: workspace.document.storyboard.scenes.map((scene) => {
        if (scene.id !== sceneId) return scene;
        const narrationChanged = patch.narrationText !== undefined && patch.narrationText !== scene.narrationText;
        const nextNarration = patch.narrationText ?? scene.narrationText;
        return {
          ...scene,
          ...patch,
          shots: narrationChanged
            ? scene.shots.map((shot) => shot.subtitleOverridden
              ? { ...shot, subtitleOutdated: true }
              : { ...shot, subtitleText: nextNarration, subtitleOutdated: false })
            : scene.shots,
        };
      }) },
    },
  })),

  updateShot: (sceneId, shotId, patch) => dirty(set, get, (workspace) => ({
    ...workspace,
    document: {
      ...workspace.document,
      storyboard: { scenes: workspace.document.storyboard.scenes.map((scene) => scene.id === sceneId
        ? { ...scene, shots: scene.shots.map((shot) => shot.id === shotId ? { ...shot, ...patch } : shot) }
        : scene) },
    },
  })),

  moveScene: (sceneId, direction) => dirty(set, get, (workspace) => {
    const scenes = moveSceneTransform(workspace.document.storyboard.scenes, sceneId, direction);
    if (scenes === workspace.document.storyboard.scenes) return workspace;
    return {
      ...workspace,
      document: {
        ...workspace.document,
        storyboard: { scenes },
      },
    };
  }),

  moveShot: (sceneId, shotId, direction) => dirty(set, get, (workspace) => ({
    ...workspace,
    document: {
      ...workspace.document,
      storyboard: { scenes: workspace.document.storyboard.scenes.map((scene) => {
        if (scene.id !== sceneId) return scene;
        const from = scene.shots.findIndex((shot) => shot.id === shotId);
        const to = from + direction;
        if (from < 0 || to < 0 || to >= scene.shots.length) return scene;
        const shots = [...scene.shots];
        [shots[from], shots[to]] = [shots[to], shots[from]];
        return { ...scene, shots: shots.map((shot, index) => ({ ...shot, index })) };
      }) },
    },
  })),

  splitShot: (sceneId, shotId, offsetMs) => {
    let splitId = "";
    dirty(set, get, (workspace) => ({
      ...workspace,
      document: {
        ...workspace.document,
        storyboard: { scenes: workspace.document.storyboard.scenes.map((scene) => {
          if (scene.id !== sceneId) return scene;
          const result = splitShotTransform(scene, shotId, offsetMs);
          splitId = result.splitId ?? "";
          return result.scene;
        }) },
      },
    }));
    if (splitId) set({ selectedSceneId: sceneId, selectedShotId: splitId });
  },

  removeShotAsset: (sceneId, shotId) => dirty(set, get, (workspace) => ({
    ...workspace,
    document: {
      ...workspace.document,
      storyboard: { scenes: workspace.document.storyboard.scenes.map((scene) => scene.id === sceneId
        ? removeShotAssetTransform(scene, shotId)
        : scene) },
    },
  })),

  duplicateShot: (sceneId, shotId) => {
    const duplicatedId = temporaryId("new-shot");
    dirty(set, get, (workspace) => ({
      ...workspace,
      document: {
        ...workspace.document,
        storyboard: { scenes: workspace.document.storyboard.scenes.map((scene) => {
          if (scene.id !== sceneId) return scene;
          const sourceIndex = scene.shots.findIndex((shot) => shot.id === shotId);
          if (sourceIndex < 0) return scene;
          const source = scene.shots[sourceIndex];
          const duplicate: Shot = {
            ...source,
            id: duplicatedId,
            index: sourceIndex + 1,
            description: source.description ? `${source.description}（副本）` : "镜头副本",
            selectedMediaVersionId: undefined,
            revision: 0,
            candidates: [],
            mediaVersions: [],
          };
          const shots = [...scene.shots];
          shots.splice(sourceIndex + 1, 0, duplicate);
          return { ...scene, shots: shots.map((shot, index) => ({ ...shot, index })) };
        }) },
      },
    }));
    set({ selectedSceneId: sceneId, selectedShotId: duplicatedId });
  },

  restoreDerivedSubtitle: (sceneId, shotId) => dirty(set, get, (workspace) => ({
    ...workspace,
    document: {
      ...workspace.document,
      storyboard: { scenes: workspace.document.storyboard.scenes.map((scene) => scene.id === sceneId
        ? {
            ...scene,
            shots: scene.shots.map((shot) => shot.id === shotId
              ? { ...shot, subtitleText: scene.narrationText, subtitleOverridden: false, subtitleOutdated: false }
              : shot),
          }
        : scene) },
    },
  })),

  addScene: () => {
    const id = temporaryId("new-scene");
    dirty(set, get, (workspace) => ({
      ...workspace,
      document: {
        ...workspace.document,
        storyboard: { scenes: [...workspace.document.storyboard.scenes, {
          id,
          index: workspace.document.storyboard.scenes.length,
          outline: `场景 ${workspace.document.storyboard.scenes.length + 1}`,
          narrationText: "",
          intent: "",
          status: "editing",
          estimatedDurationMs: 8000,
          notes: "",
          revision: 0,
          shots: [newShot(0, "")],
        }] },
      },
    }));
    set({ selectedSceneId: id, selectedShotId: get().workspace?.document.storyboard.scenes.at(-1)?.shots[0]?.id ?? null });
  },

  addShot: (sceneId) => {
    let nextId = "";
    dirty(set, get, (workspace) => ({
      ...workspace,
      document: {
        ...workspace.document,
        storyboard: { scenes: workspace.document.storyboard.scenes.map((scene) => {
          if (scene.id !== sceneId) return scene;
          const shot = newShot(scene.shots.length, scene.narrationText);
          nextId = shot.id!;
          return { ...scene, shots: [...scene.shots, shot] };
        }) },
      },
    }));
    if (nextId) set({ selectedShotId: nextId });
  },

  save: async (reason = "autosave") => {
    window.clearTimeout(autosaveTimer);
    const state = get();
    if (!state.workspace || state.saveState === "conflict") return state.workspace;
    if (savePromise) {
      await savePromise;
      if (get().saveState === "dirty") return get().save(reason);
      return get().workspace;
    }
    if (reason === "autosave" && state.saveState !== "dirty") return state.workspace;
    const startVersion = editVersion;
    const snapshot = prepareForSave(state.workspace);
    set({ saveState: "saving", saveError: null });
    savePromise = projectApi.saveWorkspace(snapshot.project.id, snapshot, reason)
      .then((server) => {
        const currentState = get();
        const current = currentState.workspace;
        if (editVersion === startVersion || !current) {
          const selection = current
            ? remapSelection(current, server, currentState.selectedSceneId, currentState.selectedShotId)
            : { selectedSceneId: null, selectedShotId: null };
          set({ workspace: server, saveState: "saved", saveError: null, ...selection });
        } else {
          const merged = mergeAfterConcurrentEdit(server, current);
          const selection = remapSelection(current, merged, currentState.selectedSceneId, currentState.selectedShotId);
          set({ workspace: merged, saveState: "dirty", saveError: null, ...selection });
          scheduleAutosave(get);
        }
        return server;
      })
      .catch((error) => {
        if (error instanceof HttpClientError && error.status === 409) {
          set({ saveState: "conflict", saveError: "服务器版本已变化，请重新加载后继续编辑" });
        } else {
          set({ saveState: "error", saveError: error instanceof Error ? error.message : "保存失败" });
        }
        throw error;
      })
      .finally(() => { savePromise = null; });
    return savePromise;
  },

  deleteScene: async (sceneId) => {
    const workspace = get().workspace;
    if (!workspace) return;
    await get().save("manual_save");
    const current = get().workspace;
    if (!current) return;
    const persisted = persistedId(sceneId)
      ?? current.document.storyboard.scenes.find((scene) => scene.id === get().selectedSceneId)?.id;
    if (!persisted) return;
    const result = await projectApi.deleteScene(current.project.id, persisted, current.document.revision);
    set({
      workspace: synchronizeWorkspace(result.workspace),
      saveState: "saved",
      selectedSceneId: result.workspace.document.storyboard.scenes[0]?.id ?? null,
      selectedShotId: result.workspace.document.storyboard.scenes[0]?.shots[0]?.id ?? null,
      undo: { token: result.undoToken, expiresAt: result.undoExpiresAt, label: "场景" },
    });
    window.clearTimeout(undoTimer);
    undoTimer = window.setTimeout(
      () => set({ undo: null }),
      Math.max(0, new Date(result.undoExpiresAt).getTime() - Date.now()),
    );
  },

  deleteShot: async (shotId) => {
    const workspace = get().workspace;
    if (!workspace) return;
    await get().save("manual_save");
    const current = get().workspace;
    if (!current) return;
    const selectedScene = current.document.storyboard.scenes.find((scene) => scene.id === get().selectedSceneId)
      ?? current.document.storyboard.scenes[0];
    const persisted = persistedId(shotId)
      ?? selectedScene?.shots.find((shot) => shot.id === get().selectedShotId)?.id;
    if (!persisted) return;
    const result = await projectApi.deleteShot(current.project.id, persisted, current.document.revision);
    const nextSelectedScene = result.workspace.document.storyboard.scenes.find((scene) => scene.id === get().selectedSceneId)
      ?? result.workspace.document.storyboard.scenes[0];
    set({
      workspace: synchronizeWorkspace(result.workspace),
      saveState: "saved",
      selectedSceneId: nextSelectedScene?.id ?? null,
      selectedShotId: nextSelectedScene?.shots[0]?.id ?? null,
      undo: { token: result.undoToken, expiresAt: result.undoExpiresAt, label: "镜头" },
    });
    window.clearTimeout(undoTimer);
    undoTimer = window.setTimeout(
      () => set({ undo: null }),
      Math.max(0, new Date(result.undoExpiresAt).getTime() - Date.now()),
    );
  },

  undoDelete: async () => {
    const { workspace, undo } = get();
    if (!workspace || !undo) return;
    const restored = await projectApi.undo(workspace.project.id, undo.token);
    window.clearTimeout(undoTimer);
    set({ workspace: synchronizeWorkspace(restored), undo: null, saveState: "saved", saveError: null });
  },

  reloadServer: async () => {
    const id = get().workspace?.project.id;
    if (id) await get().load(id);
  },

  clear: () => {
    window.clearTimeout(autosaveTimer);
    window.clearTimeout(undoTimer);
    editVersion = 0;
    set({ workspace: null, loading: false, saveState: "idle", saveError: null, selectedSceneId: null, selectedShotId: null, undo: null });
  },
}));
