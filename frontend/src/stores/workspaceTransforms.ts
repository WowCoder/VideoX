import type { ProjectDocument, Scene, Shot, TimelineItem } from "@/api/projects";

export function temporaryId(
  prefix: string,
  cryptoSource: Crypto | undefined = globalThis.crypto,
  now: () => number = Date.now,
  random: () => number = Math.random,
): string {
  if (typeof cryptoSource?.randomUUID === "function") {
    return `${prefix}-${cryptoSource.randomUUID()}`;
  }
  if (typeof cryptoSource?.getRandomValues === "function") {
    const values = cryptoSource.getRandomValues(new Uint32Array(4));
    return `${prefix}-${Array.from(values, (value) => value.toString(16).padStart(8, "0")).join("")}`;
  }
  return `${prefix}-${now().toString(36)}-${random().toString(36).slice(2)}`;
}

function clampNumber(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}

export function synchronizeTimeline(document: ProjectDocument): ProjectDocument {
  let cursorMs = 0;
  const items: TimelineItem[] = [];
  document.storyboard.scenes.forEach((scene, sceneIndex) => {
    scene.shots.forEach((shot, shotIndex) => {
      const durationMs = Math.max(100, shot.durationMs || 8000);
      items.push({
        id: `timeline-${shot.id ?? `${sceneIndex}-${shotIndex}`}`,
        shotId: shot.id,
        sceneId: scene.id,
        assetId: shot.assetId,
        mediaType: shot.assetId ? (shot.visualMode === "image" ? "image" : "video") : "gap",
        startMs: cursorMs,
        durationMs,
        sourceStartMs: shot.sourceStartMs,
        sourceEndMs: shot.sourceEndMs || shot.sourceStartMs + durationMs,
      });
      cursorMs += durationMs;
    });
  });
  const otherTracks = document.timeline.tracks.filter((track) => track.id !== "main-video");
  return {
    ...document,
    timeline: {
      durationMs: Math.max(cursorMs, ...otherTracks.flatMap((track) => (
        track.items.map((item) => item.startMs + item.durationMs)
      )), 0),
      tracks: [{ id: "main-video", kind: "video", role: "story", items }, ...otherTracks],
    },
  };
}

export function moveScene(scenes: Scene[], sceneId: string, direction: -1 | 1): Scene[] {
  const next = [...scenes];
  const from = next.findIndex((scene) => scene.id === sceneId);
  const to = from + direction;
  if (from < 0 || to < 0 || to >= next.length) return scenes;
  [next[from], next[to]] = [next[to], next[from]];
  return next.map((scene, index) => ({
    ...scene,
    index,
    shots: scene.shots.map((shot, shotIndex) => ({ ...shot, index: shotIndex })),
  }));
}

export function splitShot(
  scene: Scene,
  shotId: string,
  offsetMs: number,
  createId: () => string = () => temporaryId("new-shot"),
): { scene: Scene; splitId?: string } {
  const sourceIndex = scene.shots.findIndex((shot) => shot.id === shotId);
  if (sourceIndex < 0) return { scene };
  const source = scene.shots[sourceIndex];
  const durationMs = Math.max(200, source.durationMs);
  const firstDurationMs = clampNumber(offsetMs, 100, durationMs - 100);
  const recordedSourceSpanMs = source.sourceEndMs - source.sourceStartMs;
  const sourceSpanMs = recordedSourceSpanMs > 0 ? recordedSourceSpanMs : durationMs;
  const splitSourceMs = Math.round(
    source.sourceStartMs + sourceSpanMs * firstDurationMs / durationMs,
  );
  const splitId = createId();
  const selectedVersion = source.mediaVersions.find((version) => version.id === source.selectedMediaVersionId)
    ?? source.mediaVersions.find((version) => version.isSelected);
  const second: Shot = {
    ...source,
    id: splitId,
    index: sourceIndex + 1,
    assetId: selectedVersion?.assetId ?? source.assetId,
    selectedMediaVersionId: undefined,
    sourceStartMs: splitSourceMs,
    sourceEndMs: source.sourceEndMs || source.sourceStartMs + sourceSpanMs,
    durationMs: durationMs - firstDurationMs,
    revision: 0,
    candidates: [],
    mediaVersions: [],
  };
  const shots = [...scene.shots];
  shots.splice(
    sourceIndex,
    1,
    { ...source, durationMs: firstDurationMs, sourceEndMs: splitSourceMs },
    second,
  );
  return {
    splitId,
    scene: { ...scene, shots: shots.map((shot, index) => ({ ...shot, index })) },
  };
}

export function removeShotAsset(scene: Scene, shotId: string): Scene {
  return {
    ...scene,
    shots: scene.shots.map((shot) => shot.id === shotId
      ? {
          ...shot,
          visualMode: undefined,
          assetId: undefined,
          segmentId: undefined,
          selectedMediaVersionId: undefined,
          sourceStartMs: 0,
          sourceEndMs: shot.durationMs,
        }
      : shot),
  };
}
