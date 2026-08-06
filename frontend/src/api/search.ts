import { http } from "./client";

export type GlobalSearchType = "project" | "script" | "asset" | "clip";

export interface GlobalSearchItem {
  type: GlobalSearchType;
  id: string;
  title: string;
  subtitle: string;
  projectId?: string;
  url: string;
}

interface RawSearchResponse {
  query: string;
  total: number;
  items: Array<{
    type: GlobalSearchType;
    id: string;
    title: string;
    subtitle: string;
    project_id: string | null;
    url: string;
  }>;
}

export async function globalSearch(query: string): Promise<GlobalSearchItem[]> {
  const response = await http.get<RawSearchResponse>(
    `/search?q=${encodeURIComponent(query)}&limit=5`,
  );
  return response.items.map((item) => ({
    type: item.type,
    id: item.id,
    title: item.title,
    subtitle: item.subtitle,
    projectId: item.project_id ?? undefined,
    url: item.url,
  }));
}
