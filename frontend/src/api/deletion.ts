export interface DeleteImpact {
  entityType: "project" | "asset" | "script";
  entityId: string;
  name: string;
  canDelete: boolean;
  blockers: string[];
  counts: Record<string, number>;
}

export interface RawDeleteImpact {
  entity_type: DeleteImpact["entityType"];
  entity_id: string;
  name: string;
  can_delete: boolean;
  blockers: string[];
  counts: Record<string, number>;
}

export function mapDeleteImpact(raw: RawDeleteImpact): DeleteImpact {
  return {
    entityType: raw.entity_type,
    entityId: raw.entity_id,
    name: raw.name,
    canDelete: raw.can_delete,
    blockers: raw.blockers ?? [],
    counts: raw.counts ?? {},
  };
}
