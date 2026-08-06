"""根据任务真实类型生成准确的通知跳转链接。

Revision ID: 007_notification_links
Revises: 006_user_settings
Create Date: 2026-08-01
"""

from typing import Sequence, Union

from alembic import op


revision: str = "007_notification_links"
down_revision: Union[str, None] = "006_user_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION create_job_terminal_notification()
        RETURNS trigger AS $$
        DECLARE
            owner_user_id varchar(50);
            target_link varchar(500);
            target_script_id varchar(64);
        BEGIN
            IF NEW.status IN ('SUCCEEDED', 'FAILED')
               AND OLD.status IS DISTINCT FROM NEW.status THEN
                SELECT owner_id INTO owner_user_id FROM projects WHERE id = NEW.project_id;

                IF NEW.type = '素材处理' THEN
                    target_link := '/workspace/library';
                ELSIF NEW.type IN ('导出', 'AI 初剪生成') THEN
                    target_link := '/workspace/projects/' || NEW.project_id || '/editor';
                ELSIF NEW.type = '镜头匹配' AND COALESCE(NEW.payload->>'script_id', '') <> '' THEN
                    target_link := '/workspace/scripts/' || (NEW.payload->>'script_id') || '/editor';
                ELSIF NEW.type IN ('AI 生图分镜', '分镜图 AI 生视频', '示意图特效视频') THEN
                    SELECT scripts.id INTO target_script_id
                    FROM shots
                    JOIN script_units ON script_units.id = shots.unit_id
                    JOIN scripts ON scripts.id = script_units.script_id
                    WHERE shots.id = NEW.payload->>'shot_id';
                    target_link := CASE
                        WHEN target_script_id IS NOT NULL
                            THEN '/workspace/scripts/' || target_script_id || '/editor'
                        ELSE '/workspace/projects/' || NEW.project_id
                    END;
                ELSE
                    target_link := '/workspace/projects/' || NEW.project_id;
                END IF;

                IF owner_user_id IS NOT NULL THEN
                    INSERT INTO notifications (
                        id, user_id, project_id, job_id, type, title,
                        message, link, is_read, created_at
                    ) VALUES (
                        'notification-' || substr(md5(random()::text || clock_timestamp()::text), 1, 12),
                        owner_user_id,
                        NEW.project_id,
                        NEW.id,
                        CASE WHEN NEW.status = 'SUCCEEDED' THEN 'success' ELSE 'error' END,
                        CASE WHEN NEW.status = 'SUCCEEDED' THEN NEW.name || '已完成' ELSE NEW.name || '失败' END,
                        COALESCE(NULLIF(NEW.result_detail, ''), NULLIF(NEW.detail, ''),
                            CASE WHEN NEW.status = 'SUCCEEDED' THEN '任务已完成' ELSE '任务执行失败' END),
                        target_link,
                        false,
                        now()
                    );
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION create_job_terminal_notification()
        RETURNS trigger AS $$
        DECLARE owner_user_id varchar(50);
        BEGIN
            IF NEW.status IN ('SUCCEEDED', 'FAILED') AND OLD.status IS DISTINCT FROM NEW.status THEN
                SELECT owner_id INTO owner_user_id FROM projects WHERE id = NEW.project_id;
                IF owner_user_id IS NOT NULL THEN
                    INSERT INTO notifications (
                        id, user_id, project_id, job_id, type, title,
                        message, link, is_read, created_at
                    ) VALUES (
                        'notification-' || substr(md5(random()::text || clock_timestamp()::text), 1, 12),
                        owner_user_id, NEW.project_id, NEW.id,
                        CASE WHEN NEW.status = 'SUCCEEDED' THEN 'success' ELSE 'error' END,
                        CASE WHEN NEW.status = 'SUCCEEDED' THEN NEW.name || '已完成' ELSE NEW.name || '失败' END,
                        COALESCE(NULLIF(NEW.result_detail, ''), NULLIF(NEW.detail, ''), '任务状态已更新'),
                        '/workspace/projects/' || NEW.project_id, false, now()
                    );
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
