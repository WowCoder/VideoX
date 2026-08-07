"""cut versions, generation history, and imported asset lineage

Revision ID: 017_cut_versions_history
Revises: 016_audio_assets
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "017_cut_versions_history"
down_revision: str | None = "016_audio_assets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("assets", sa.Column("imported_from_asset_id", sa.String(length=64), nullable=True))
    op.create_foreign_key(
        "fk_assets_imported_from_asset_id", "assets", "assets",
        ["imported_from_asset_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_assets_imported_from_asset_id", "assets", ["imported_from_asset_id"])

    op.create_table(
        "cut_versions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("snapshot_script_id", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=50), server_default="AI 初剪生成中", nullable=False),
        sa.Column("aspect_ratio", sa.String(length=10), server_default="16:9", nullable=False),
        sa.Column("timeline", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("timeline_version", sa.Integer(), server_default="0", nullable=False),
        sa.Column("timeline_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["snapshot_script_id"], ["scripts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "name", name="uq_cut_version_project_name"),
    )
    op.create_index("ix_cut_versions_project_id", "cut_versions", ["project_id"])
    op.create_index("ix_cut_versions_snapshot_script_id", "cut_versions", ["snapshot_script_id"])

    # 每个历史剪辑项目补一个 V1，保留原时间线和并发版本号。
    op.execute(
        """
        INSERT INTO cut_versions (
            id, project_id, snapshot_script_id, name, status, aspect_ratio,
            timeline, timeline_version, timeline_updated_at, created_at, updated_at
        )
        SELECT
            'cut-' || substr(md5(random()::text || p.id), 1, 12),
            p.id,
            (
                SELECT s.id FROM scripts s
                WHERE s.project_id = p.id AND s.is_snapshot = true
                ORDER BY s.created_at DESC LIMIT 1
            ),
            'V1', p.status, COALESCE(p.aspect_ratio, '16:9'),
            COALESCE(p.timeline, '[]'::json), COALESCE(p.timeline_version, 0),
            p.timeline_updated_at, p.created_at, p.updated_at
        FROM projects p
        WHERE p.source_script_id IS NOT NULL
        """
    )

    op.create_table(
        "shot_generations",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("shot_id", sa.String(length=64), nullable=False),
        sa.Column("job_id", sa.String(length=64), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("storage_path", sa.String(length=1000), nullable=False),
        sa.Column("prompt", sa.Text(), server_default="", nullable=False),
        sa.Column("is_selected", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["shot_id"], ["shots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "kind", name="uq_shot_generation_job_kind"),
    )
    op.create_index("ix_shot_generations_shot_id", "shot_generations", ["shot_id"])
    op.create_index("ix_shot_generations_job_id", "shot_generations", ["job_id"])
    op.create_index("ix_shot_generations_kind", "shot_generations", ["kind"])
    op.create_index("ix_shot_generations_is_selected", "shot_generations", ["is_selected"])

    for column, kind in (
        ("generated_image_path", "image"),
        ("generated_video_path", "video"),
        ("generated_effect_video_path", "effect"),
    ):
        op.execute(
            f"""
            INSERT INTO shot_generations (
                id, shot_id, job_id, kind, storage_path, prompt, is_selected, created_at
            )
            SELECT
                'generation-' || substr(md5(random()::text || id || '{kind}'), 1, 12),
                id, NULL, '{kind}', {column}, '', true, created_at
            FROM shots WHERE {column} IS NOT NULL
            """
        )

    # 旧模型允许三个路径同时存在；按视频 > 特效 > 图片的展示优先级只采用一个。
    op.execute(
        """
        UPDATE shot_generations sg
        SET is_selected = CASE
            WHEN sg.kind = 'video' AND s.generated_video_path IS NOT NULL THEN true
            WHEN sg.kind = 'effect' AND s.generated_video_path IS NULL
                AND s.generated_effect_video_path IS NOT NULL THEN true
            WHEN sg.kind = 'image' AND s.generated_video_path IS NULL
                AND s.generated_effect_video_path IS NULL
                AND s.generated_image_path IS NOT NULL THEN true
            ELSE false
        END
        FROM shots s
        WHERE s.id = sg.shot_id
        """
    )


def downgrade() -> None:
    op.drop_index("ix_shot_generations_is_selected", table_name="shot_generations")
    op.drop_index("ix_shot_generations_kind", table_name="shot_generations")
    op.drop_index("ix_shot_generations_job_id", table_name="shot_generations")
    op.drop_index("ix_shot_generations_shot_id", table_name="shot_generations")
    op.drop_table("shot_generations")
    op.drop_index("ix_cut_versions_snapshot_script_id", table_name="cut_versions")
    op.drop_index("ix_cut_versions_project_id", table_name="cut_versions")
    op.drop_table("cut_versions")
    op.drop_index("ix_assets_imported_from_asset_id", table_name="assets")
    op.drop_constraint("fk_assets_imported_from_asset_id", "assets", type_="foreignkey")
    op.drop_column("assets", "imported_from_asset_id")
