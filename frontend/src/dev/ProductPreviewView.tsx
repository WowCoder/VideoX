import { useState } from "react";
import WorkspaceCreationFlow from "@/components/WorkspaceCreationFlow";
import type { WorkspaceCreationSource } from "@/lib/workspaceCreationDraft";
import LibraryView from "@/views/LibraryView";
import InspirationView from "@/views/InspirationView";
import {
  previewAssets,
  previewInspirationRuns,
  previewInspirationTasks,
  previewProjects,
} from "./productPreview";

const creationPreviewAssets = previewAssets.map((asset) => ({
  ...asset,
  processingStatus: "ready",
}));

export default function ProductPreviewView({ type }: { type: "library" | "inspiration" | "creation" }) {
  if (type === "library") {
    return <LibraryView previewAssets={previewAssets} previewProjects={previewProjects} />;
  }
  if (type === "inspiration") {
    return <InspirationView previewTasks={previewInspirationTasks} previewRuns={previewInspirationRuns} />;
  }
  return <CreationFlowPreview />;
}

function CreationFlowPreview() {
  const [source, setSource] = useState<WorkspaceCreationSource>("write-script");
  return <main className="mx-auto w-full max-w-[1280px] px-5 pb-16 pt-8 sm:px-7 lg:px-8 lg:pt-10"><WorkspaceCreationFlow initialSource={source} onSourceChange={setSource} onExit={() => undefined} previewAssets={creationPreviewAssets} /></main>;
}
