"""Project workspace architecture and global assets.

Revision ID: 021_project_workspace
Revises: 020_team_seats

This migration splits multi-script projects into one-project/one-document
aggregates, preserves cut versions as ProjectRevision history, and archives
removed collaboration state before dropping legacy tables.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "021_project_workspace"
down_revision: str | None = "020_team_seats"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Immutable migration archive and future project revision history.
    op.create_table(
        "project_revisions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(50), server_default="autosave", nullable=False),
        sa.Column("document_snapshot", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("created_by", sa.String(50), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("metadata", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("project_id", "revision", name="uq_project_revision_number"),
    )
    op.create_index("ix_project_revisions_project_id", "project_revisions", ["project_id"])
    op.create_index("ix_project_revisions_reason", "project_revisions", ["reason"])

    # Keep a queryable, row-level account of every recovery/split decision.  The
    # migration is intentionally irreversible, so this table is the durable
    # reconciliation report rather than a transient console log.
    op.create_table(
        "migration_audits",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("migration_name", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("source_id", sa.String(64), nullable=True),
        sa.Column("target_id", sa.String(64), nullable=True),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("details", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_migration_audits_migration_name", "migration_audits", ["migration_name"])
    op.create_index("ix_migration_audits_source_id", "migration_audits", ["source_id"])

    op.execute(
        """
        INSERT INTO project_revisions (
            id, project_id, revision, reason, document_snapshot, created_by, metadata, created_at
        )
        SELECT
            'revision-' || substr(md5(random()::text || p.id), 1, 12),
            p.id,
            0,
            'migration_archive',
            json_build_object(
                'legacy_project', row_to_json(p),
                'scripts', COALESCE((
                    SELECT json_agg(row_to_json(s) ORDER BY s.updated_at DESC)
                    FROM scripts s WHERE s.project_id = p.id
                ), '[]'::json),
                'cut_versions', COALESCE((
                    SELECT json_agg(row_to_json(cv) ORDER BY cv.updated_at DESC)
                    FROM cut_versions cv WHERE cv.project_id = p.id
                ), '[]'::json),
                'project_media', COALESCE((
                    SELECT json_agg(row_to_json(pmi) ORDER BY pmi.created_at DESC)
                    FROM project_media_items pmi WHERE pmi.project_id = p.id
                ), '[]'::json),
                'collaboration', json_build_object(
                    'members', COALESCE((
                        SELECT json_agg(row_to_json(pm)) FROM project_members pm WHERE pm.project_id = p.id
                    ), '[]'::json),
                    'invitations', COALESCE((
                        SELECT json_agg(row_to_json(pi)) FROM project_invitations pi WHERE pi.project_id = p.id
                    ), '[]'::json)
                )
            ),
            p.owner_id,
            json_build_object('source', '021_project_workspace'),
            now()
        FROM projects p
        """
    )

    # Projects become stable aggregate roots.
    op.add_column("projects", sa.Column("cover_asset_id", sa.String(64), nullable=True))
    op.add_column("projects", sa.Column("master_output_asset_id", sa.String(64), nullable=True))
    op.create_foreign_key(
        "fk_projects_cover_asset", "projects", "assets", ["cover_asset_id"], ["id"], ondelete="SET NULL"
    )
    op.create_foreign_key(
        "fk_projects_master_output_asset", "projects", "assets", ["master_output_asset_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_projects_status", "projects", ["status"])
    op.create_index("ix_projects_updated_at", "projects", ["updated_at"])
    op.execute(
        """
        UPDATE projects SET status = CASE
            WHEN status IN ('处理中', 'AI 初剪生成中') THEN 'processing'
            WHEN status IN ('全部可搜索', 'AI 初剪可编辑') THEN 'ready'
            WHEN status IN ('脚本编辑中', '脚本已导入') THEN 'editing'
            ELSE 'draft'
        END
        """
    )

    # Global assets and unified segments.
    op.add_column("assets", sa.Column("owner_id", sa.String(50), nullable=True))
    op.add_column("assets", sa.Column("source_type", sa.String(30), server_default="upload", nullable=False))
    op.add_column("assets", sa.Column("processing_status", sa.String(30), server_default="pending", nullable=False))
    op.add_column("assets", sa.Column("mime_type", sa.String(120), nullable=True))
    op.add_column("assets", sa.Column("checksum", sa.String(128), nullable=True))
    op.add_column("assets", sa.Column("width", sa.Integer(), nullable=True))
    op.add_column("assets", sa.Column("height", sa.Integer(), nullable=True))
    op.add_column("assets", sa.Column("duration_ms", sa.Integer(), server_default="0", nullable=False))
    op.add_column("assets", sa.Column("recognition", sa.JSON(), server_default="{}", nullable=False))
    op.add_column("assets", sa.Column("ai_provider", sa.String(80), nullable=True))
    op.add_column("assets", sa.Column("ai_model", sa.String(160), nullable=True))
    op.add_column("assets", sa.Column("ai_prompt", sa.Text(), nullable=True))
    op.add_column("assets", sa.Column("metadata", sa.JSON(), server_default="{}", nullable=False))
    op.add_column("assets", sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.add_column("assets", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        """
        UPDATE assets a
        SET owner_id = p.owner_id,
            duration_ms = GREATEST(0, round(COALESCE(a.duration, 0) * 1000)::integer),
            processing_status = CASE
                WHEN a.status = '处理完成' THEN 'ready'
                WHEN a.status = '处理失败' THEN 'failed'
                ELSE 'processing'
            END,
            status = CASE
                WHEN a.status = '处理完成' THEN 'ready'
                WHEN a.status = '处理失败' THEN 'failed'
                ELSE 'processing'
            END,
            source_type = CASE WHEN a.source = '用户上传' THEN 'upload' ELSE 'derived' END,
            width = CASE WHEN split_part(COALESCE(a.resolution, ''), 'x', 1) ~ '^[0-9]+$'
                         THEN split_part(a.resolution, 'x', 1)::integer END,
            height = CASE WHEN split_part(COALESCE(a.resolution, ''), 'x', 2) ~ '^[0-9]+$'
                          THEN split_part(a.resolution, 'x', 2)::integer END
        FROM projects p
        WHERE p.id = a.project_id
        """
    )
    op.alter_column("assets", "owner_id", nullable=False)
    op.create_foreign_key("fk_assets_owner", "assets", "users", ["owner_id"], ["id"], ondelete="CASCADE")
    op.create_index("ix_assets_owner_id", "assets", ["owner_id"])
    op.create_index("ix_assets_source_type", "assets", ["source_type"])
    op.create_index("ix_assets_processing_status", "assets", ["processing_status"])
    op.create_index("ix_assets_checksum", "assets", ["checksum"])
    op.create_index("ix_assets_deleted_at", "assets", ["deleted_at"])
    op.create_index("ix_assets_owner_media_created", "assets", ["owner_id", "media_type", "created_at"])
    op.create_index("ix_assets_owner_source_created", "assets", ["owner_id", "source_type", "created_at"])
    op.create_index("ix_assets_owner_processing_created", "assets", ["owner_id", "processing_status", "created_at"])

    op.rename_table("clips", "asset_segments")
    op.execute("ALTER INDEX IF EXISTS ix_clips_asset_id RENAME TO ix_asset_segments_asset_id")
    op.execute("ALTER INDEX IF EXISTS ix_clips_embedding RENAME TO ix_asset_segments_embedding")
    op.add_column("asset_segments", sa.Column("start_ms", sa.Integer(), server_default="0", nullable=False))
    op.add_column("asset_segments", sa.Column("end_ms", sa.Integer(), server_default="0", nullable=False))
    op.add_column("asset_segments", sa.Column("tags", sa.JSON(), server_default="[]", nullable=False))
    op.add_column("asset_segments", sa.Column("recognition", sa.JSON(), server_default="{}", nullable=False))
    op.execute(
        """
        UPDATE asset_segments
        SET start_ms = GREATEST(0, round(COALESCE(start_time, 0) * 1000)::integer),
            end_ms = GREATEST(0, round(COALESCE(end_time, 0) * 1000)::integer),
            recognition = json_build_object(
                'spaces', CASE WHEN scene_type IS NULL THEN '[]'::json ELSE json_build_array(scene_type) END,
                'people', COALESCE(persons, '[]'::json),
                'objects', COALESCE(objects, '[]'::json),
                'actions', CASE WHEN camera_motion IS NULL THEN '[]'::json ELSE json_build_array(camera_motion) END,
                'shotType', shot_type
            )
        """
    )
    op.alter_column("asset_segments", "transcript_segment", new_column_name="transcript")
    op.alter_column("asset_segments", "ocr_segment", new_column_name="ocr_text")
    for column in ("start_time", "end_time", "duration", "scene_type", "shot_type", "camera_motion", "persons", "objects", "variant"):
        op.drop_column("asset_segments", column)

    op.create_table(
        "project_asset_links",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_id", sa.String(64), sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(30), server_default="source", nullable=False),
        sa.Column("linked_by", sa.String(50), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("linked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("project_id", "asset_id", "role", name="uq_project_asset_role"),
    )
    op.create_index("ix_project_asset_links_project_id", "project_asset_links", ["project_id"])
    op.create_index("ix_project_asset_links_asset_id", "project_asset_links", ["asset_id"])
    op.create_index("ix_project_asset_links_project_linked", "project_asset_links", ["project_id", "linked_at"])
    op.execute(
        """
        INSERT INTO project_asset_links (id, project_id, asset_id, role, linked_by, linked_at)
        SELECT 'asset-link-' || substr(md5(random()::text || a.id), 1, 12),
               a.project_id, a.id, 'source', p.owner_id, COALESCE(a.created_at, now())
        FROM assets a JOIN projects p ON p.id = a.project_id
        ON CONFLICT (project_id, asset_id, role) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO assets (
            id, project_id, owner_id, name, media_type, source_type, status, processing_status,
            file_path, preview_path, thumbnail_path, file_size_mb, duration_ms,
            has_audio, tags, recognition, metadata, uploaded_at, created_at, updated_at
        )
        SELECT 'asset-' || substr(md5('project-media:' || pmi.id), 1, 24),
               pmi.project_id, p.owner_id, pmi.name, pmi.media_type,
               CASE WHEN pmi.kind LIKE 'ai_%' THEN 'ai_generated' ELSE 'derived' END,
               'ready', 'ready', pmi.storage_path, pmi.storage_path, pmi.thumbnail_path,
               0, GREATEST(0, round(COALESCE(pmi.duration, 0) * 1000)::integer),
               false, '[]'::json, '{}'::json,
               json_build_object('legacy_project_media_id', pmi.id, 'legacy_kind', pmi.kind),
               pmi.created_at, pmi.created_at, pmi.created_at
        FROM project_media_items pmi
        JOIN projects p ON p.id = pmi.project_id
        WHERE pmi.asset_id IS NULL AND pmi.storage_path IS NOT NULL
        ON CONFLICT (id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO project_asset_links (id, project_id, asset_id, role, linked_by, linked_at)
        SELECT 'asset-link-' || substr(md5('project-media:' || pmi.id), 1, 12),
               pmi.project_id,
               'asset-' || substr(md5('project-media:' || pmi.id), 1, 24),
               CASE WHEN pmi.kind LIKE 'ai_%' THEN 'shot_media' ELSE 'source' END,
               p.owner_id, pmi.created_at
        FROM project_media_items pmi
        JOIN projects p ON p.id = pmi.project_id
        WHERE pmi.asset_id IS NULL AND pmi.storage_path IS NOT NULL
        ON CONFLICT (project_id, asset_id, role) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO project_asset_links (id, project_id, asset_id, role, linked_by, linked_at)
        SELECT 'asset-link-' || substr(md5(random()::text || pmi.id), 1, 12),
               pmi.project_id, pmi.asset_id, 'source', p.owner_id, pmi.created_at
        FROM project_media_items pmi
        JOIN projects p ON p.id = pmi.project_id
        WHERE pmi.asset_id IS NOT NULL
        ON CONFLICT (project_id, asset_id, role) DO NOTHING
        """
    )

    # Jobs may now represent global asset and inspiration work.
    op.add_column("jobs", sa.Column("owner_id", sa.String(50), nullable=True))
    op.add_column("jobs", sa.Column("subject_type", sa.String(40), nullable=True))
    op.add_column("jobs", sa.Column("subject_id", sa.String(64), nullable=True))
    op.execute("UPDATE jobs j SET owner_id = p.owner_id FROM projects p WHERE p.id = j.project_id")
    op.alter_column("jobs", "owner_id", nullable=False)
    op.create_foreign_key("fk_jobs_owner", "jobs", "users", ["owner_id"], ["id"], ondelete="CASCADE")
    op.create_index("ix_jobs_owner_id", "jobs", ["owner_id"])
    op.create_index("ix_jobs_subject_type", "jobs", ["subject_type"])
    op.create_index("ix_jobs_subject_id", "jobs", ["subject_id"])
    op.execute("ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_project_id_fkey")
    op.alter_column("jobs", "project_id", nullable=True)
    op.create_foreign_key("fk_jobs_project", "jobs", "projects", ["project_id"], ["id"], ondelete="SET NULL")
    op.execute(
        """
        INSERT INTO assets (
            id, project_id, owner_id, name, media_type, source_type, status, processing_status,
            file_path, preview_path, file_size_mb, duration_ms, has_audio,
            tags, recognition, metadata, uploaded_at, created_at, updated_at
        )
        SELECT 'asset-' || substr(md5('export:' || j.id), 1, 24),
               j.project_id, j.owner_id, COALESCE(NULLIF(j.name, ''), '主成片导出'), 'video',
               'render_output', 'ready', 'ready', j.result_path, j.result_path,
               0, 0, true, '[]'::json, '{}'::json,
               json_build_object('export_job_id', j.id),
               COALESCE(j.updated_at, j.created_at), j.created_at, COALESCE(j.updated_at, j.created_at)
        FROM jobs j
        WHERE j.type = '导出' AND j.status = 'SUCCEEDED' AND j.result_path IS NOT NULL
        ON CONFLICT (id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO project_asset_links (id, project_id, asset_id, role, linked_by, linked_at)
        SELECT 'asset-link-' || substr(md5('export:' || j.id), 1, 12), j.project_id,
               'asset-' || substr(md5('export:' || j.id), 1, 24), 'render_output',
               j.owner_id, COALESCE(j.updated_at, j.created_at)
        FROM jobs j
        WHERE j.project_id IS NOT NULL AND j.type = '导出' AND j.status = 'SUCCEEDED'
          AND j.result_path IS NOT NULL
        ON CONFLICT (project_id, asset_id, role) DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE projects p SET master_output_asset_id = latest.asset_id
        FROM (
            SELECT DISTINCT ON (j.project_id) j.project_id,
                   'asset-' || substr(md5('export:' || j.id), 1, 24) AS asset_id
            FROM jobs j
            WHERE j.project_id IS NOT NULL AND j.type = '导出' AND j.status = 'SUCCEEDED'
              AND j.result_path IS NOT NULL
            ORDER BY j.project_id, j.updated_at DESC
        ) latest
        WHERE latest.project_id = p.id
        """
    )

    # Script/scene/shot canonical document fields.
    op.add_column("scripts", sa.Column("target_duration_seconds", sa.Integer(), nullable=True))
    op.add_column("scripts", sa.Column("estimated_duration_seconds", sa.Integer(), server_default="0", nullable=False))
    op.add_column("scripts", sa.Column("revision", sa.Integer(), server_default="0", nullable=False))
    op.execute(
        """
        UPDATE scripts SET
            status = CASE WHEN status IN ('已完成', '初剪可编辑') THEN 'ready'
                          WHEN status = '初剪生成中' THEN 'processing' ELSE 'editing' END,
            estimated_duration_seconds = COALESCE((
                SELECT sum(su.duration) FROM script_units su WHERE su.script_id = scripts.id
            ), 0),
            target_duration_seconds = COALESCE((
                SELECT sum(su.duration) FROM script_units su WHERE su.script_id = scripts.id
            ), 0)
        """
    )

    op.alter_column("script_units", "text", new_column_name="narration_text")
    op.add_column("script_units", sa.Column("estimated_duration_ms", sa.Integer(), server_default="8000", nullable=False))
    op.add_column("script_units", sa.Column("revision", sa.Integer(), server_default="0", nullable=False))
    op.add_column("script_units", sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.execute("UPDATE script_units SET estimated_duration_ms = GREATEST(0, duration * 1000)")

    op.alter_column("shots", "selected_clip_id", new_column_name="segment_id")
    op.add_column("shots", sa.Column("asset_id", sa.String(64), nullable=True))
    op.add_column("shots", sa.Column("selected_media_version_id", sa.String(64), nullable=True))
    op.add_column("shots", sa.Column("source_start_ms", sa.Integer(), server_default="0", nullable=False))
    op.add_column("shots", sa.Column("source_end_ms", sa.Integer(), server_default="0", nullable=False))
    op.add_column("shots", sa.Column("duration_ms", sa.Integer(), server_default="8000", nullable=False))
    op.add_column("shots", sa.Column("locked", sa.Boolean(), server_default=sa.false(), nullable=False))
    for name, default in (
        ("transform", "{}"), ("adjust", "{}"), ("audio_settings", "{}"),
        ("subtitle_settings", "{}"), ("transition", "{}"), ("motion", "{}"),
    ):
        op.add_column("shots", sa.Column(name, sa.JSON(), server_default=default, nullable=False))
    op.add_column("shots", sa.Column("subtitle_text", sa.Text(), server_default="", nullable=False))
    op.add_column("shots", sa.Column("subtitle_overridden", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("shots", sa.Column("subtitle_source_revision", sa.Integer(), server_default="0", nullable=False))
    op.add_column("shots", sa.Column("revision", sa.Integer(), server_default="0", nullable=False))
    op.add_column("shots", sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_foreign_key("fk_shots_asset", "shots", "assets", ["asset_id"], ["id"], ondelete="SET NULL")
    op.execute(
        """
        UPDATE shots s SET
            asset_id = seg.asset_id,
            source_start_ms = seg.start_ms,
            source_end_ms = seg.end_ms,
            duration_ms = GREATEST(0, s.duration * 1000)
        FROM asset_segments seg WHERE seg.id = s.segment_id
        """
    )
    op.execute(
        """
        UPDATE shots s SET subtitle_text = su.narration_text
        FROM script_units su WHERE su.id = s.unit_id AND COALESCE(s.subtitle_text, '') = ''
        """
    )

    # Give legacy unit-level candidates a deterministic recovery shot when the
    # unit did not contain one.  This avoids deleting useful matching results
    # merely because the old UI allowed a candidate before a shot existed.
    op.execute(
        """
        INSERT INTO shots (id, unit_id, index, description, status, duration, notes, created_at)
        SELECT 'shot-' || substr(md5('021-candidate-recovery:' || c.unit_id), 1, 24),
               c.unit_id, 0, '迁移恢复镜头', 'editing', 8, '由旧版候选素材恢复', now()
        FROM candidates c
        WHERE c.shot_id IS NULL AND c.unit_id IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM shots s WHERE s.unit_id = c.unit_id)
        GROUP BY c.unit_id
        """
    )
    # Normalize unit candidates onto their first shot, then keep only shot candidates.
    op.execute(
        """
        UPDATE candidates c
        SET shot_id = (
            SELECT s.id FROM shots s WHERE s.unit_id = c.unit_id ORDER BY s.index LIMIT 1
        )
        WHERE c.shot_id IS NULL AND c.unit_id IS NOT NULL
        """
    )
    op.execute(
        """
        INSERT INTO migration_audits (
            id, migration_name, entity_type, source_id, action, details
        )
        SELECT 'audit-' || substr(md5('021-orphan-candidate:' || c.id), 1, 24),
               '021_project_workspace', 'candidate', c.id, 'archived_orphan', row_to_json(c)
        FROM candidates c WHERE c.shot_id IS NULL
        """
    )
    op.execute("DELETE FROM candidates WHERE shot_id IS NULL")
    op.alter_column("candidates", "shot_id", nullable=False)
    op.alter_column("candidates", "clip_id", new_column_name="segment_id")
    op.add_column("candidates", sa.Column("range_start_ms", sa.Integer(), server_default="0", nullable=False))
    op.add_column("candidates", sa.Column("range_end_ms", sa.Integer(), server_default="0", nullable=False))
    op.drop_column("candidates", "unit_id")
    op.drop_column("candidates", "range_start")
    op.drop_column("candidates", "range_end")
    op.drop_column("candidates", "variant")
    op.create_index("ix_candidates_segment_id", "candidates", ["segment_id"])

    # Convert every old generated path into a first-class global Asset and media version.
    op.create_table(
        "shot_media_versions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("shot_id", sa.String(64), sa.ForeignKey("shots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_id", sa.String(64), sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.String(64), sa.ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("parent_version_id", sa.String(64), sa.ForeignKey("shot_media_versions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("operation", sa.String(50), server_default="generated", nullable=False),
        sa.Column("parameters", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("status", sa.String(20), server_default="ready", nullable=False),
        sa.Column("is_selected", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("job_id", "kind", name="uq_shot_media_version_job_kind"),
    )
    for column in ("shot_id", "asset_id", "job_id", "kind", "status", "is_selected"):
        op.create_index(f"ix_shot_media_versions_{column}", "shot_media_versions", [column])
    op.execute(
        """
        INSERT INTO assets (
            id, project_id, owner_id, name, media_type, source_type, status, processing_status,
            file_path, preview_path, thumbnail_path, file_size_mb, duration_ms,
            has_audio, tags, recognition, metadata, uploaded_at, created_at, updated_at
        )
        SELECT
            'asset-' || substr(md5('generation:' || sg.id), 1, 24),
            sc.project_id,
            p.owner_id,
            COALESCE(NULLIF(s.description, ''), 'AI 生成媒体'),
            CASE WHEN sg.kind = 'image' THEN 'image' ELSE 'video' END,
            'ai_generated', 'ready', 'ready', sg.storage_path, sg.storage_path,
            CASE WHEN sg.kind = 'image' THEN sg.storage_path ELSE NULL END,
            0, GREATEST(0, s.duration * 1000), false, '[]'::json, '{}'::json,
            json_build_object('legacy_generation_id', sg.id, 'prompt', sg.prompt),
            sg.created_at, sg.created_at, sg.created_at
        FROM shot_generations sg
        JOIN shots s ON s.id = sg.shot_id
        JOIN script_units su ON su.id = s.unit_id
        JOIN scripts sc ON sc.id = su.script_id
        JOIN projects p ON p.id = sc.project_id
        ON CONFLICT (id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO shot_media_versions (
            id, shot_id, asset_id, job_id, kind, operation, parameters, status, is_selected, created_at
        )
        SELECT
            'media-version-' || substr(md5('generation:' || sg.id), 1, 20),
            sg.shot_id,
            'asset-' || substr(md5('generation:' || sg.id), 1, 24),
            sg.job_id,
            CASE sg.kind WHEN 'image' THEN 'generated_image'
                         WHEN 'video' THEN 'generated_video' ELSE 'effect_video' END,
            'generated', json_build_object('prompt', sg.prompt), 'ready', sg.is_selected, sg.created_at
        FROM shot_generations sg
        """
    )
    op.execute(
        """
        UPDATE shots s SET selected_media_version_id = selected.id, asset_id = selected.asset_id
        FROM (
            SELECT DISTINCT ON (shot_id) id, shot_id, asset_id
            FROM shot_media_versions
            WHERE is_selected = true
            ORDER BY shot_id, created_at DESC
        ) selected
        WHERE selected.shot_id = s.id
        """
    )
    op.create_foreign_key(
        "fk_shots_selected_media_version", "shots", "shot_media_versions",
        ["selected_media_version_id"], ["id"], ondelete="SET NULL"
    )
    op.execute(
        """
        INSERT INTO project_asset_links (id, project_id, asset_id, role, linked_by, linked_at)
        SELECT 'asset-link-' || substr(md5(random()::text || smv.id), 1, 12),
               sc.project_id, smv.asset_id, 'shot_media', p.owner_id, smv.created_at
        FROM shot_media_versions smv
        JOIN shots s ON s.id = smv.shot_id
        JOIN script_units su ON su.id = s.unit_id
        JOIN scripts sc ON sc.id = su.script_id
        JOIN projects p ON p.id = sc.project_id
        ON CONFLICT (project_id, asset_id, role) DO NOTHING
        """
    )

    # One composition per project, populated from the latest real cut settings.
    op.create_table(
        "project_compositions",
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("revision", sa.Integer(), server_default="0", nullable=False),
        sa.Column("aspect_ratio", sa.String(10), server_default="16:9", nullable=False),
        sa.Column("resolution", sa.String(20), server_default="1920x1080", nullable=False),
        sa.Column("fps", sa.Integer(), server_default="25", nullable=False),
        sa.Column("visual_settings", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("global_audio", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("global_overlays", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("timeline", sa.JSON(), server_default='{"duration_ms":0,"tracks":[]}', nullable=False),
        sa.Column("visual_layers", sa.JSON(), server_default='{"items":[]}', nullable=False),
        sa.Column("global_scopes", sa.JSON(), server_default='{"film":{},"scenes":{}}', nullable=False),
        sa.Column("workflow_graph", sa.JSON(), server_default='{"nodes":[],"edges":[]}', nullable=False),
        sa.Column("render_settings", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("current_render_asset_id", sa.String(64), sa.ForeignKey("assets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "project_undo_tokens",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("operation", sa.String(30), nullable=False),
        sa.Column("payload", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("base_revision", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_project_undo_tokens_project_id", "project_undo_tokens", ["project_id"])
    op.create_index("ix_project_undo_tokens_expires_at", "project_undo_tokens", ["expires_at"])

    # One ProjectDocument per project: retain the selected/current business
    # script on the old project and split every additional business or snapshot
    # script into a deterministic recovery project.  No scene/shot subtree is
    # deleted.  Keeping snapshots as recovery projects makes their structured
    # content inspectable after the legacy cut-version UI is removed.
    op.execute(
        """
        CREATE TEMPORARY TABLE _021_script_split ON COMMIT DROP AS
        SELECT old_project_id, script_id,
               'project-' || substr(md5('021-split:' || old_project_id || ':' || script_id), 1, 24) AS new_project_id,
               is_snapshot
        FROM (
            SELECT p.id AS old_project_id, s.id AS script_id, s.is_snapshot,
                   row_number() OVER (
                PARTITION BY p.id
                ORDER BY CASE WHEN s.id = p.source_script_id THEN 0
                              WHEN NOT s.is_snapshot THEN 1 ELSE 2 END,
                         s.updated_at DESC, s.created_at DESC, s.id
            ) AS rn
            FROM projects p
            JOIN scripts s ON s.project_id = p.id
        ) ranked
        WHERE ranked.rn > 1
        """
    )
    op.execute(
        """
        INSERT INTO projects (
            id, owner_id, name, initial, type, description, status,
            asset_count, clip_count, script_count, variant, members, is_new,
            source_script_id, visual_style, aspect_ratio, ai_shot_count,
            timeline, timeline_version, timeline_updated_at,
            cover_asset_id, master_output_asset_id, created_at, updated_at
        )
        SELECT m.new_project_id, p.owner_id,
               left(p.name || CASE WHEN m.is_snapshot THEN ' — 历史版本：' ELSE ' — ' END || s.title, 200),
               p.initial, p.type, p.description, 'draft',
               p.asset_count, p.clip_count, 1, p.variant, p.members, false,
               s.id, p.visual_style, p.aspect_ratio, p.ai_shot_count,
               p.timeline, p.timeline_version, p.timeline_updated_at,
               p.cover_asset_id, p.master_output_asset_id, p.created_at, p.updated_at
        FROM _021_script_split m
        JOIN projects p ON p.id = m.old_project_id
        JOIN scripts s ON s.id = m.script_id
        """
    )
    op.execute(
        """
        UPDATE scripts s SET project_id = m.new_project_id
        FROM _021_script_split m
        WHERE s.id = m.script_id
        """
    )
    op.execute(
        """
        INSERT INTO project_asset_links (id, project_id, asset_id, role, linked_by, linked_at)
        SELECT 'asset-link-' || substr(md5('021-split-link:' || m.new_project_id || ':' || l.asset_id || ':' || l.role), 1, 24),
               m.new_project_id, l.asset_id, l.role, l.linked_by, l.linked_at
        FROM _021_script_split m
        JOIN project_asset_links l ON l.project_id = m.old_project_id
        ON CONFLICT (project_id, asset_id, role) DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE jobs j SET project_id = m.new_project_id
        FROM _021_script_split m
        WHERE j.project_id = m.old_project_id
          AND (
              j.payload->>'script_id' = m.script_id
              OR (j.subject_type IN ('script', 'project_document') AND j.subject_id = m.script_id)
              OR EXISTS (
                  SELECT 1 FROM script_units su
                  JOIN shots sh ON sh.unit_id = su.id
                  WHERE su.script_id = m.script_id
                    AND (j.payload->>'shot_id' = sh.id OR j.subject_id = sh.id)
              )
          )
        """
    )
    op.execute(
        """
        INSERT INTO migration_audits (
            id, migration_name, entity_type, source_id, target_id, action, details
        )
        SELECT 'audit-' || substr(md5('021-script-split:' || m.script_id), 1, 24),
               '021_project_workspace', 'script', m.script_id, m.new_project_id,
               CASE WHEN m.is_snapshot THEN 'snapshot_recovery_project' ELSE 'split_project' END,
               json_build_object(
                   'old_project_id', m.old_project_id,
                   'scene_count', (SELECT count(*) FROM script_units su WHERE su.script_id = m.script_id),
                   'shot_count', (SELECT count(*) FROM shots sh JOIN script_units su ON su.id = sh.unit_id WHERE su.script_id = m.script_id)
               )
        FROM _021_script_split m
        """
    )
    op.execute(
        """
        INSERT INTO project_revisions (
            id, project_id, revision, reason, document_snapshot, created_by, metadata, created_at
        )
        SELECT 'revision-' || substr(md5('021-script-split:' || m.script_id), 1, 24),
               m.new_project_id, 0, 'migration_split_recovery',
               json_build_object(
                   'project', row_to_json(p),
                   'document', json_build_object(
                       'id', s.id,
                       'schema_version', 1,
                       'revision', 0,
                       'legacy_script', row_to_json(s)
                   )
               ),
               p.owner_id,
               json_build_object(
                   'source', 'scripts',
                   'old_project_id', m.old_project_id,
                   'is_snapshot', m.is_snapshot
               ),
               COALESCE(s.updated_at, p.updated_at)
        FROM _021_script_split m
        JOIN projects p ON p.id = m.new_project_id
        JOIN scripts s ON s.id = m.script_id
        """
    )

    # Create a canonical composition for every resulting project.  Legacy
    # timeline arrays are kept verbatim as tracks; a cut tied to the project's
    # script wins, otherwise the old project timeline is retained as recovery
    # data instead of being reduced to a boolean flag.
    op.execute(
        """
        INSERT INTO project_compositions (
            project_id, revision, aspect_ratio, timeline, visual_layers,
            global_scopes, workflow_graph, render_settings,
            current_render_asset_id, created_at, updated_at
        )
        SELECT p.id, 0,
               COALESCE(selected_cut.aspect_ratio, p.aspect_ratio, '16:9'),
               json_build_object(
                   'duration_ms', 0,
                   'tracks', COALESCE(selected_cut.timeline, p.timeline, '[]'::json)
               ),
               '{"items":[]}'::json,
               '{"film":{},"scenes":{}}'::json,
               '{"nodes":[],"edges":[]}'::json,
               json_build_object(
                   'migrated_from_legacy_timeline',
                   CASE WHEN selected_cut.id IS NOT NULL OR COALESCE(json_array_length(p.timeline), 0) > 0
                        THEN true ELSE false END,
                   'legacy_cut_version_id', selected_cut.id
               ),
               p.master_output_asset_id, p.created_at, p.updated_at
        FROM projects p
        LEFT JOIN scripts s ON s.project_id = p.id
        LEFT JOIN LATERAL (
            SELECT cv.id, cv.aspect_ratio, cv.timeline
            FROM cut_versions cv
            WHERE cv.snapshot_script_id = s.id
               OR (cv.snapshot_script_id IS NULL AND cv.project_id = p.id)
            ORDER BY CASE WHEN cv.snapshot_script_id = s.id THEN 0 ELSE 1 END,
                     cv.updated_at DESC, cv.id
            LIMIT 1
        ) selected_cut ON true
        """
    )

    # Every legacy cut remains available as an immutable revision, including
    # cuts that were not selected as the current composition.
    op.execute(
        """
        WITH resolved AS (
            SELECT cv.*,
                   COALESCE(s.project_id, cv.project_id) AS target_project_id
            FROM cut_versions cv
            LEFT JOIN scripts s ON s.id = cv.snapshot_script_id
        ), numbered AS (
            SELECT resolved.*,
                   row_number() OVER (
                       PARTITION BY target_project_id ORDER BY updated_at, id
                   ) AS target_revision
            FROM resolved
        )
        INSERT INTO project_revisions (
            id, project_id, revision, reason, document_snapshot, created_by, metadata, created_at
        )
        SELECT 'revision-' || substr(md5('021-cut:' || numbered.id), 1, 24),
               target_project_id, target_revision, 'migration_cut_recovery',
               json_build_object(
                   'legacy_cut_version', row_to_json(numbered),
                   'document', json_build_object(
                       'schema_version', 1,
                       'timeline', json_build_object('duration_ms', 0, 'tracks', numbered.timeline)
                   )
               ),
               p.owner_id,
               json_build_object('source', 'cut_versions', 'legacy_cut_version_id', numbered.id),
               numbered.created_at
        FROM numbered
        JOIN projects p ON p.id = numbered.target_project_id
        """
    )
    op.execute("UPDATE projects SET source_script_id = NULL")
    op.execute("DROP TABLE cut_versions")
    op.execute("DROP TABLE project_media_items")
    op.execute("DROP TABLE shot_generations")
    op.execute(
        """
        INSERT INTO scripts (
            id, project_id, title, summary, status, visual_config, source_type,
            target_duration_seconds, estimated_duration_seconds, revision, created_at, updated_at
        )
        SELECT 'script-' || substr(md5('021-blank:' || p.id), 1, 24), p.id, p.name, '', 'editing',
               '{"stylePreset":"brand-tech","aspectRatio":"16:9","references":{"characters":[],"objects":[],"spaces":[]}}'::json,
               'blank', NULL, 0, 0, now(), now()
        FROM projects p
        WHERE NOT EXISTS (SELECT 1 FROM scripts s WHERE s.project_id = p.id)
        """
    )
    op.create_unique_constraint("uq_scripts_project_id", "scripts", ["project_id"])

    # Formal inspiration domain.
    op.create_table(
        "inspiration_tasks",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("owner_id", sa.String(50), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("task_type", sa.String(40), nullable=False),
        sa.Column("topic_brief", sa.Text(), server_default="", nullable=False),
        sa.Column("topic_count", sa.Integer(), nullable=True),
        sa.Column(
            "schedule",
            sa.JSON(),
            server_default='{"type":"daily","time":"09:00","weekday":1,"time_zone":"Asia/Shanghai"}',
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_inspiration_tasks_owner_id", "inspiration_tasks", ["owner_id"])
    op.create_index("ix_inspiration_tasks_task_type", "inspiration_tasks", ["task_type"])
    op.create_index("ix_inspiration_tasks_enabled", "inspiration_tasks", ["enabled"])
    op.create_index("ix_inspiration_tasks_next_run_at", "inspiration_tasks", ["next_run_at"])

    op.create_table(
        "inspiration_sources",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("task_id", sa.String(64), sa.ForeignKey("inspiration_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_type", sa.String(30), server_default="web", nullable=False),
        sa.Column("url", sa.String(2000), nullable=False),
        sa.Column("fetch_config", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_inspiration_sources_task_id", "inspiration_sources", ["task_id"])

    op.create_table(
        "inspiration_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("task_id", sa.String(64), sa.ForeignKey("inspiration_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.String(64), sa.ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, unique=True),
        sa.Column("status", sa.String(20), server_default="QUEUED", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_inspiration_runs_task_id", "inspiration_runs", ["task_id"])
    op.create_index("ix_inspiration_runs_status", "inspiration_runs", ["status"])

    op.create_table(
        "inspiration_source_snapshots",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("source_id", sa.String(64), sa.ForeignKey("inspiration_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("inspiration_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("etag", sa.String(500), nullable=True),
        sa.Column("last_modified", sa.String(500), nullable=True),
        sa.Column("content_type", sa.String(120), nullable=True),
        sa.Column("raw_content", sa.Text(), server_default="", nullable=False),
        sa.Column("cleaned_content", sa.Text(), server_default="", nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source_id", "run_id", name="uq_inspiration_source_run"),
    )
    op.create_index("ix_inspiration_source_snapshots_source_id", "inspiration_source_snapshots", ["source_id"])
    op.create_index("ix_inspiration_source_snapshots_run_id", "inspiration_source_snapshots", ["run_id"])

    op.create_table(
        "inspiration_results",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("inspiration_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("summary", sa.Text(), server_default="", nullable=False),
        sa.Column("content", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("citations", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("model_provider", sa.String(80), nullable=True),
        sa.Column("model_name", sa.String(160), nullable=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_inspiration_results_run_id", "inspiration_results", ["run_id"])

    # Remove collaboration and all redundant legacy columns.
    op.drop_table("project_invitations")
    op.drop_table("project_members")
    op.drop_constraint("ck_memberships_seat_quota_positive", "memberships", type_="check")
    op.drop_column("memberships", "seat_quota")

    op.execute("ALTER TABLE projects DROP CONSTRAINT IF EXISTS fk_projects_source_script_id")
    for column in (
        "asset_count", "clip_count", "script_count", "members", "is_new", "source_script_id",
        "visual_style", "aspect_ratio", "ai_shot_count", "timeline", "timeline_version", "timeline_updated_at",
    ):
        op.drop_column("projects", column)

    op.execute("ALTER TABLE assets DROP CONSTRAINT IF EXISTS fk_assets_imported_from_asset_id")
    op.execute("ALTER TABLE assets DROP CONSTRAINT IF EXISTS assets_project_id_fkey")
    for index in ("ix_assets_imported_from_asset_id", "ix_assets_project_id"):
        op.execute(f"DROP INDEX IF EXISTS {index}")
    for column in ("project_id", "imported_from_asset_id", "duration", "source", "variant", "resolution"):
        op.drop_column("assets", column)

    op.execute("ALTER TABLE scripts DROP CONSTRAINT IF EXISTS fk_scripts_parent_script_id")
    for index in ("ix_scripts_is_snapshot", "ix_scripts_parent_script_id"):
        op.execute(f"DROP INDEX IF EXISTS {index}")
    for column in (
        "duration", "unit_count", "matched_count", "progress", "variant", "format",
        "needs_initial_save", "is_snapshot", "parent_script_id",
    ):
        op.drop_column("scripts", column)

    op.execute("ALTER TABLE script_units DROP CONSTRAINT IF EXISTS fk_script_units_source_unit_id")
    op.execute("DROP INDEX IF EXISTS ix_script_units_source_unit_id")
    for column in ("source_unit_id", "selected_clip_id", "duration", "candidates"):
        op.drop_column("script_units", column)

    op.execute("ALTER TABLE shots DROP CONSTRAINT IF EXISTS fk_shots_source_shot_id")
    op.execute("DROP INDEX IF EXISTS ix_shots_source_shot_id")
    for column in (
        "source_shot_id", "duration", "generated_image_path", "generated_video_path",
        "generated_effect_video_path", "candidates",
    ):
        op.drop_column("shots", column)


def downgrade() -> None:
    raise RuntimeError(
        "021_project_workspace is intentionally irreversible: split scripts, cut versions "
        "and removed collaboration rows are preserved in recovery projects, revisions, "
        "and migration_audits."
    )
