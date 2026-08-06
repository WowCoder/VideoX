"""初始迁移：建表 + pgvector 扩展 + 初始化会员方案。

Revision ID: 001_initial
Revises:
Create Date: 2026-07-29
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# DashScope text-embedding-v3 维度
EMBEDDING_DIM = 1024


def upgrade() -> None:
    # 1. 启用 pgvector 扩展
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 2. memberships 表
    op.create_table(
        "memberships",
        sa.Column("id", sa.String(50), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("rank", sa.Integer, server_default="0"),
        sa.Column("billing_cycle", sa.String(20), server_default="monthly"),
        sa.Column("processing_minutes", sa.Integer, server_default="60"),
        sa.Column("ai_image_quota", sa.Integer, server_default="10"),
        sa.Column("ai_video_quota", sa.Integer, server_default="5"),
        sa.Column("storage_gb", sa.Integer, server_default="5"),
        sa.Column("export_quota", sa.Integer, server_default="10"),
        sa.Column("price", sa.Float, server_default="0.0"),
        sa.Column("payment_method", sa.String(50), nullable=True),
    )

    # 3. users 表
    op.create_table(
        "users",
        sa.Column("id", sa.String(50), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("avatar_initial", sa.String(4), server_default="U"),
        sa.Column("membership_id", sa.String(50), sa.ForeignKey("memberships.id"), server_default="membership-free"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # 4. usages 表
    op.create_table(
        "usages",
        sa.Column("id", sa.String(50), primary_key=True),
        sa.Column("user_id", sa.String(50), sa.ForeignKey("users.id"), unique=True, nullable=False),
        sa.Column("processing_minutes_used", sa.Integer, server_default="0"),
        sa.Column("ai_image_used", sa.Integer, server_default="0"),
        sa.Column("ai_video_used", sa.Integer, server_default="0"),
        sa.Column("storage_used_mb", sa.Float, server_default="0.0"),
        sa.Column("export_used", sa.Integer, server_default="0"),
        sa.Column("billing_cycle_start", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("billing_cycle_end", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # 5. projects 表（先不建 source_script_id FK，避免循环依赖）
    op.create_table(
        "projects",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("owner_id", sa.String(50), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("initial", sa.String(4), server_default="P"),
        sa.Column("type", sa.String(50), server_default="AI 科技 / 产品讲解"),
        sa.Column("description", sa.Text, server_default=""),
        sa.Column("status", sa.String(50), server_default="等待上传"),
        sa.Column("asset_count", sa.Integer, server_default="0"),
        sa.Column("clip_count", sa.Integer, server_default="0"),
        sa.Column("script_count", sa.Integer, server_default="0"),
        sa.Column("variant", sa.String(50), server_default="stage"),
        sa.Column("members", sa.JSON, server_default="[]"),
        sa.Column("is_new", sa.Boolean, server_default="false"),
        sa.Column("source_script_id", sa.String(64), nullable=True),  # FK 延后添加
        sa.Column("visual_style", sa.String(50), nullable=True),
        sa.Column("aspect_ratio", sa.String(10), nullable=True),
        sa.Column("ai_shot_count", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.String(50), server_default="刚刚"),
    )

    # 6. assets 表
    op.create_table(
        "assets",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("duration", sa.Float, server_default="0.0"),
        sa.Column("status", sa.String(50), server_default="处理中"),
        sa.Column("source", sa.String(100), server_default="用户上传"),
        sa.Column("variant", sa.String(50), server_default="stage"),
        sa.Column("file_path", sa.String(500), nullable=True),
        sa.Column("file_size_mb", sa.Float, server_default="0.0"),
        sa.Column("resolution", sa.String(20), nullable=True),
        sa.Column("fps", sa.Float, server_default="25.0"),
        sa.Column("codec", sa.String(50), nullable=True),
        sa.Column("transcript", sa.Text, nullable=True),
        sa.Column("ocr_text", sa.Text, nullable=True),
        sa.Column("tags", sa.JSON, server_default="[]"),
        sa.Column("uploaded_at", sa.String(50), server_default="刚刚"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # 7. clips 表
    op.create_table(
        "clips",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("asset_id", sa.String(64), sa.ForeignKey("assets.id"), nullable=False, index=True),
        sa.Column("start_time", sa.Float, server_default="0.0"),
        sa.Column("end_time", sa.Float, server_default="0.0"),
        sa.Column("duration", sa.Float, server_default="0.0"),
        sa.Column("title", sa.String(200), server_default=""),
        sa.Column("transcript_segment", sa.Text, server_default=""),
        sa.Column("ocr_segment", sa.Text, server_default=""),
        sa.Column("scene_type", sa.String(50), nullable=True),
        sa.Column("shot_type", sa.String(50), nullable=True),
        sa.Column("camera_motion", sa.String(50), nullable=True),
        sa.Column("persons", sa.JSON, server_default="[]"),
        sa.Column("objects", sa.JSON, server_default="[]"),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True),
        sa.Column("thumbnail_path", sa.String(500), nullable=True),
        sa.Column("variant", sa.String(50), server_default="stage"),
        sa.Column("quality_score", sa.Float, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # 8. scripts 表
    op.create_table(
        "scripts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False, index=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("summary", sa.Text, server_default=""),
        sa.Column("status", sa.String(50), server_default="编辑中"),
        sa.Column("duration", sa.String(10), server_default="00:00"),
        sa.Column("unit_count", sa.Integer, server_default="0"),
        sa.Column("matched_count", sa.Integer, server_default="0"),
        sa.Column("progress", sa.Integer, server_default="0"),
        sa.Column("variant", sa.String(50), server_default="stage"),
        sa.Column("format", sa.String(20), server_default="横屏 16:9"),
        sa.Column("visual_config", sa.JSON, server_default='{"stylePreset": "brand-tech"}'),
        sa.Column("needs_initial_save", sa.Boolean, server_default="true"),
        sa.Column("source_type", sa.String(20), server_default="blank"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.String(50), server_default="刚刚"),
    )

    # 9. 补充 projects.source_script_id 的 FK（循环依赖解决）
    op.create_foreign_key(
        "fk_projects_source_script_id",
        "projects",
        "scripts",
        ["source_script_id"],
        ["id"],
    )

    # 10. script_units 表
    op.create_table(
        "script_units",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("script_id", sa.String(64), sa.ForeignKey("scripts.id"), nullable=False, index=True),
        sa.Column("index", sa.Integer, server_default="0"),
        sa.Column("outline", sa.String(200), server_default=""),
        sa.Column("text", sa.Text, server_default=""),
        sa.Column("intent", sa.Text, server_default=""),
        sa.Column("status", sa.String(50), server_default="待编辑"),
        sa.Column("selected_clip_id", sa.String(64), sa.ForeignKey("clips.id"), nullable=True),
        sa.Column("duration", sa.Integer, server_default="8"),
        sa.Column("notes", sa.Text, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("candidates", sa.JSON, server_default="[]"),
    )

    # 11. shots 表
    op.create_table(
        "shots",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("unit_id", sa.String(64), sa.ForeignKey("script_units.id"), nullable=False, index=True),
        sa.Column("index", sa.Integer, server_default="0"),
        sa.Column("description", sa.Text, server_default=""),
        sa.Column("status", sa.String(50), server_default="待编辑"),
        sa.Column("selected_clip_id", sa.String(64), sa.ForeignKey("clips.id"), nullable=True),
        sa.Column("visual_mode", sa.String(20), nullable=True),
        sa.Column("duration", sa.Integer, server_default="8"),
        sa.Column("notes", sa.Text, server_default=""),
        sa.Column("generated_image_path", sa.String(500), nullable=True),
        sa.Column("generated_video_path", sa.String(500), nullable=True),
        sa.Column("sketch_data", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("candidates", sa.JSON, server_default="[]"),
    )

    # 12. candidates 表
    op.create_table(
        "candidates",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("shot_id", sa.String(64), sa.ForeignKey("shots.id"), nullable=True, index=True),
        sa.Column("unit_id", sa.String(64), sa.ForeignKey("script_units.id"), nullable=True, index=True),
        sa.Column("clip_id", sa.String(64), sa.ForeignKey("clips.id"), nullable=True),
        sa.Column("title", sa.String(200), server_default=""),
        sa.Column("source", sa.String(255), server_default=""),
        sa.Column("range_start", sa.String(20), server_default=""),
        sa.Column("range_end", sa.String(20), server_default=""),
        sa.Column("score", sa.Integer, server_default="0"),
        sa.Column("reason", sa.Text, server_default=""),
        sa.Column("variant", sa.String(50), server_default="stage"),
        sa.Column("low_confidence", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # 13. jobs 表
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False, index=True),
        sa.Column("name", sa.String(200), server_default=""),
        sa.Column("type", sa.String(50), server_default=""),
        sa.Column("status", sa.String(20), server_default="QUEUED"),
        sa.Column("stage", sa.String(100), server_default=""),
        sa.Column("stages", sa.JSON, server_default="[]"),
        sa.Column("stage_index", sa.Integer, server_default="0"),
        sa.Column("progress", sa.Integer, server_default="0"),
        sa.Column("detail", sa.Text, server_default=""),
        sa.Column("eta", sa.String(100), server_default="预计 1-2 分钟"),
        sa.Column("logs", sa.JSON, server_default="[]"),
        sa.Column("result", sa.String(200), nullable=True),
        sa.Column("result_detail", sa.Text, server_default=""),
        sa.Column("is_simulated", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # 14. 初始化会员方案
    op.execute("""
        INSERT INTO memberships (id, name, rank, billing_cycle, processing_minutes, ai_image_quota, ai_video_quota, storage_gb, export_quota, price)
        VALUES
            ('membership-free', 'Free', 0, 'monthly', 60, 10, 5, 5, 10, 0.0),
            ('membership-pro', 'Pro', 1, 'monthly', 600, 100, 50, 50, 100, 99.0),
            ('membership-team', 'Team', 2, 'monthly', 3000, 500, 200, 200, 500, 399.0)
        ON CONFLICT (id) DO NOTHING
    """)

    # 15. 索引：加速语义检索
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_clips_embedding ON clips USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )


def downgrade() -> None:
    op.drop_table("jobs")
    op.drop_table("candidates")
    op.drop_table("shots")
    op.drop_table("script_units")
    op.drop_table("scripts")
    op.drop_table("clips")
    op.drop_table("assets")
    op.drop_table("projects")
    op.drop_table("usages")
    op.drop_table("users")
    op.drop_table("memberships")
