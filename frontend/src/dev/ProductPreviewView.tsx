import LibraryView from "@/views/LibraryView";
import InspirationView from "@/views/InspirationView";
import {
  previewAssets,
  previewInspirationRuns,
  previewInspirationTasks,
  previewProjects,
} from "./productPreview";

export default function ProductPreviewView({ type }: { type: "library" | "inspiration" }) {
  if (type === "library") {
    return <LibraryView previewAssets={previewAssets} previewProjects={previewProjects} />;
  }
  return <InspirationView previewTasks={previewInspirationTasks} previewRuns={previewInspirationRuns} />;
}
