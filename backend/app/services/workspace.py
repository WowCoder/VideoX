"""项目工作区聚合读写、版本历史以及场景/镜头撤销。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.asset import Asset, AssetSegment, ProjectAssetLink
from app.models.job import Job
from app.models.project import Project, ProjectComposition, ProjectRevision, ProjectUndoToken
from app.models.script import Candidate, Script, ScriptUnit, Shot, ShotMediaVersion
from app.models.user import User
from app.schemas.project import (
    GlobalScopesDocument,
    ProjectDocument,
    ProjectDocumentSettings,
    ProjectOut,
    SceneDocument,
    ShotDocument,
    ShotMediaVersionDocument,
    StoryboardDocument,
    TimelineDocument,
    VisualLayersDocument,
    WorkflowGraphDocument,
    WorkspaceOut,
    WorkspaceSave,
)
from app.utils.storage import get_file_url


def _safe_media_url(path: str | None) -> str | None:
    if not path:
        return None
    if path.startswith(("http://", "https://", "data:")):
        return path
    try:
        return get_file_url(path)
    except Exception:
        return None


def _media_version_document(version: ShotMediaVersion) -> ShotMediaVersionDocument:
    return ShotMediaVersionDocument(
        id=version.id,
        asset_id=version.asset_id,
        job_id=version.job_id,
        parent_version_id=version.parent_version_id,
        kind=version.kind,
        operation=version.operation,
        parameters=version.parameters or {},
        status=version.status,
        is_selected=version.is_selected,
        media_url=_safe_media_url(version.asset.file_path if getattr(version, "asset", None) else None),
        created_at=version.created_at,
    )


def shot_document(shot: Shot, scene_revision: int) -> ShotDocument:
    return ShotDocument(
        id=shot.id,
        index=shot.index,
        description=shot.description,
        status=shot.status,
        visual_mode=shot.visual_mode,
        asset_id=shot.asset_id,
        segment_id=shot.segment_id,
        selected_media_version_id=shot.selected_media_version_id,
        source_start_ms=shot.source_start_ms,
        source_end_ms=shot.source_end_ms,
        duration_ms=shot.duration_ms,
        locked=shot.locked,
        transform=shot.transform or {},
        adjust=shot.adjust or {},
        audio_settings=shot.audio_settings or {},
        subtitle_settings=shot.subtitle_settings or {},
        transition=shot.transition or {},
        motion=shot.motion or {},
        subtitle_text=shot.subtitle_text,
        subtitle_overridden=shot.subtitle_overridden,
        subtitle_source_revision=shot.subtitle_source_revision,
        subtitle_outdated=bool(
            shot.subtitle_overridden and shot.subtitle_source_revision < scene_revision
        ),
        notes=shot.notes,
        sketch_data=shot.sketch_data,
        revision=shot.revision,
        candidates=[
            {
                "id": item.id,
                "segment_id": item.segment_id,
                "title": item.title,
                "source": item.source,
                "range_start_ms": item.range_start_ms,
                "range_end_ms": item.range_end_ms,
                "score": item.score,
                "reason": item.reason,
                "low_confidence": item.low_confidence,
            }
            for item in shot.candidates
        ],
        media_versions=[_media_version_document(item) for item in shot.media_versions],
    )


def scene_document(scene: ScriptUnit) -> SceneDocument:
    return SceneDocument(
        id=scene.id,
        index=scene.index,
        outline=scene.outline,
        narration_text=scene.narration_text,
        intent=scene.intent,
        status=scene.status,
        estimated_duration_ms=scene.estimated_duration_ms,
        notes=scene.notes,
        revision=scene.revision,
        shots=[shot_document(shot, scene.revision) for shot in scene.shots],
    )


def _timeline_document(value: dict | None, script: Script) -> TimelineDocument:
    raw = value or {}
    raw_tracks = raw.get("tracks", [])
    structured_tracks = [
        track
        for track in raw_tracks
        if isinstance(track, dict) and isinstance(track.get("items"), list)
    ]
    other_tracks = [track for track in structured_tracks if track.get("id") != "main-video"]
    legacy_items = [track for track in raw_tracks if track not in structured_tracks]
    if legacy_items:
        other_tracks.append(
            {
                "id": "legacy-recovery",
                "kind": "overlay",
                "role": "legacy_recovery",
                "items": legacy_items,
            }
        )
    cursor_ms = 0
    main_items: list[dict] = []
    for scene in script.units:
        for shot in scene.shots:
            duration_ms = max(100, shot.duration_ms or 8000)
            main_items.append(
                {
                    "id": f"timeline-{shot.id}",
                    "shotId": shot.id,
                    "sceneId": scene.id,
                    "assetId": shot.asset_id,
                    "mediaType": (
                        "gap" if not shot.asset_id
                        else "image" if shot.visual_mode == "image"
                        else "video"
                    ),
                    "startMs": cursor_ms,
                    "durationMs": duration_ms,
                    "sourceStartMs": shot.source_start_ms or 0,
                    "sourceEndMs": shot.source_end_ms or (shot.source_start_ms or 0) + duration_ms,
                }
            )
            cursor_ms += duration_ms
    other_end_ms = max(
        (
            int(item.get("startMs", 0) or 0) + int(item.get("durationMs", 0) or 0)
            for track in other_tracks
            for item in track.get("items", [])
            if isinstance(item, dict)
        ),
        default=0,
    )
    return TimelineDocument(
        duration_ms=max(cursor_ms, other_end_ms),
        tracks=[
            {"id": "main-video", "kind": "video", "role": "story", "items": main_items},
            *other_tracks,
        ],
    )


def project_document(project: Project) -> ProjectDocument:
    script = project.script
    composition = project.composition
    global_scopes = composition.global_scopes or {}
    return ProjectDocument(
        id=script.id,
        schema_version=1,
        revision=script.revision,
        settings=ProjectDocumentSettings(
            title=script.title,
            summary=script.summary,
            status=script.status,
            target_duration_seconds=script.target_duration_seconds,
            estimated_duration_seconds=script.estimated_duration_seconds,
            source_type=script.source_type,
            visual_config=script.visual_config or {},
            aspect_ratio=composition.aspect_ratio,
            resolution=composition.resolution,
            fps=composition.fps,
            visual_settings=composition.visual_settings or {},
            global_audio=composition.global_audio or {},
            global_overlays=composition.global_overlays or [],
        ),
        storyboard=StoryboardDocument(
            scenes=[scene_document(scene) for scene in script.units]
        ),
        timeline=_timeline_document(composition.timeline, script),
        visual_layers=VisualLayersDocument(**(composition.visual_layers or {"items": []})),
        global_scopes=GlobalScopesDocument(
            film=global_scopes.get("film", {}),
            scenes=global_scopes.get("scenes", {}),
        ),
        workflow_graph=WorkflowGraphDocument(
            **(composition.workflow_graph or {"nodes": [], "edges": []})
        ),
        render_settings=composition.render_settings or {},
        current_render_asset_id=composition.current_render_asset_id,
    )


async def load_project_workspace(
    db: AsyncSession,
    project_id: str,
    owner_id: str,
    *,
    for_update: bool = False,
) -> Project:
    query = (
        select(Project)
        .where(Project.id == project_id, Project.owner_id == owner_id)
        .options(
            selectinload(Project.composition),
            selectinload(Project.asset_links).selectinload(ProjectAssetLink.asset),
            selectinload(Project.script)
            .selectinload(Script.units)
            .selectinload(ScriptUnit.shots)
            .selectinload(Shot.candidates),
            selectinload(Project.script)
            .selectinload(Script.units)
            .selectinload(ScriptUnit.shots)
            .selectinload(Shot.media_versions)
            .selectinload(ShotMediaVersion.asset),
        )
    )
    if for_update:
        query = query.with_for_update()
    project = (await db.execute(query)).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    if not project.script or not project.composition:
        raise HTTPException(status_code=500, detail="项目工作区数据不完整，请先执行数据修复")
    return project


async def project_out(db: AsyncSession, project: Project) -> ProjectOut:
    asset_count = (
        await db.execute(
            select(func.count()).select_from(ProjectAssetLink).where(
                ProjectAssetLink.project_id == project.id
            )
        )
    ).scalar() or 0
    scene_count = len(project.script.units) if project.script else 0
    shots = [shot for scene in project.script.units for shot in scene.shots] if project.script else []
    shot_count = len(shots)
    duration_ms = sum(max(0, shot.duration_ms or 0) for shot in shots)
    matched_shot_count = sum(
        1 for shot in shots if shot.asset_id or shot.selected_media_version_id
    )
    matched_percent = round(matched_shot_count * 100 / shot_count) if shot_count else 0
    linked_assets = [
        link.asset
        for link in (getattr(project, "asset_links", []) or [])
        if getattr(link, "asset", None) is not None and link.asset.deleted_at is None
    ]
    cover_candidates = [
        project.cover_asset_id,
        project.master_output_asset_id,
        project.composition.current_render_asset_id if project.composition else None,
    ]
    cover_asset = next(
        (
            asset
            for asset_id in cover_candidates
            if asset_id
            for asset in linked_assets
            if asset.id == asset_id
        ),
        None,
    )
    if cover_asset is None:
        cover_asset = next(
            (asset for asset in linked_assets if asset.media_type in {"image", "video"}),
            None,
        )
    active_jobs = (
        await db.execute(
            select(func.count()).select_from(Job).where(
                Job.project_id == project.id,
                Job.status.in_(["QUEUED", "RUNNING", "PAUSED"]),
            )
        )
    ).scalar() or 0
    return ProjectOut.model_validate(project).model_copy(
        update={
            "asset_count": int(asset_count),
            "scene_count": scene_count,
            "shot_count": shot_count,
            "duration_ms": duration_ms,
            "aspect_ratio": project.composition.aspect_ratio if project.composition else "16:9",
            "matched_percent": matched_percent,
            "cover_media_type": cover_asset.media_type if cover_asset else None,
            "cover_media_url": _safe_media_url(
                (cover_asset.preview_path or cover_asset.file_path) if cover_asset else None
            ),
            "cover_thumbnail_url": _safe_media_url(
                cover_asset.thumbnail_path if cover_asset else None
            ),
            "active_job_count": int(active_jobs),
        }
    )


async def workspace_out(db: AsyncSession, project: Project) -> WorkspaceOut:
    from app.api.assets import asset_out

    return WorkspaceOut(
        project=await project_out(db, project),
        document=project_document(project),
        linked_assets=[asset_out(link.asset, include_segments=False) for link in project.asset_links],
    )


def _snapshot(project: Project) -> dict:
    return {
        "project": {
            "id": project.id,
            "name": project.name,
            "type": project.type,
            "description": project.description,
            "status": project.status,
            "variant": project.variant,
            "cover_asset_id": project.cover_asset_id,
            "master_output_asset_id": project.master_output_asset_id,
        },
        "document": project_document(project).model_dump(mode="json"),
    }


async def record_revision(
    db: AsyncSession,
    project: Project,
    user_id: str,
    reason: str,
    metadata: dict | None = None,
) -> None:
    db.add(
        ProjectRevision(
            project_id=project.id,
            revision=project.script.revision,
            reason=reason,
            document_snapshot=_snapshot(project),
            created_by=user_id,
            revision_metadata=metadata or {},
        )
    )


async def _validate_asset_references(
    db: AsyncSession,
    owner_id: str,
    scenes: list[SceneDocument],
) -> dict[str, AssetSegment]:
    asset_ids = {shot.asset_id for scene in scenes for shot in scene.shots if shot.asset_id}
    segment_ids = {shot.segment_id for scene in scenes for shot in scene.shots if shot.segment_id}
    if asset_ids:
        owned = set(
            (
                await db.execute(
                    select(Asset.id).where(
                        Asset.owner_id == owner_id,
                        Asset.deleted_at.is_(None),
                        Asset.id.in_(asset_ids),
                    )
                )
            ).scalars().all()
        )
        if owned != asset_ids:
            raise HTTPException(status_code=422, detail="镜头引用了不存在或无权使用的素材")
    segments: dict[str, AssetSegment] = {}
    if segment_ids:
        rows = (
            await db.execute(
                select(AssetSegment)
                .join(Asset)
                .where(Asset.owner_id == owner_id, AssetSegment.id.in_(segment_ids))
            )
        ).scalars().all()
        segments = {item.id: item for item in rows}
        if set(segments) != segment_ids:
            raise HTTPException(status_code=422, detail="镜头引用了不存在的素材片段")
    for scene in scenes:
        for shot in scene.shots:
            if shot.segment_id:
                segment = segments[shot.segment_id]
                if shot.asset_id and segment.asset_id != shot.asset_id:
                    raise HTTPException(status_code=422, detail="镜头素材与素材片段不匹配")
    return segments


async def _link_used_assets(
    db: AsyncSession,
    project: Project,
    user_id: str,
    scenes: list[SceneDocument],
) -> None:
    asset_ids = {shot.asset_id for scene in scenes for shot in scene.shots if shot.asset_id}
    if not asset_ids:
        return
    existing = set(
        (
            await db.execute(
                select(ProjectAssetLink.asset_id).where(
                    ProjectAssetLink.project_id == project.id,
                    ProjectAssetLink.asset_id.in_(asset_ids),
                )
            )
        ).scalars().all()
    )
    for asset_id in asset_ids - existing:
        db.add(
            ProjectAssetLink(
                project_id=project.id,
                asset_id=asset_id,
                role="shot_media",
                linked_by=user_id,
            )
        )


def _apply_shot(
    shot: Shot,
    incoming: ShotDocument,
    scene: ScriptUnit,
    narration_changed: bool,
    segment: AssetSegment | None,
) -> None:
    old_subtitle = shot.subtitle_text
    shot.index = incoming.index
    shot.description = incoming.description
    shot.status = incoming.status
    shot.visual_mode = incoming.visual_mode
    shot.asset_id = incoming.asset_id or (segment.asset_id if segment else None)
    shot.segment_id = incoming.segment_id
    shot.source_start_ms = incoming.source_start_ms if not segment else max(incoming.source_start_ms, segment.start_ms)
    shot.source_end_ms = incoming.source_end_ms or (segment.end_ms if segment else 0)
    shot.duration_ms = incoming.duration_ms
    shot.locked = incoming.locked
    shot.transform = incoming.transform
    shot.adjust = incoming.adjust
    shot.audio_settings = incoming.audio_settings
    shot.subtitle_settings = incoming.subtitle_settings
    shot.transition = incoming.transition
    shot.motion = incoming.motion
    shot.notes = incoming.notes
    shot.sketch_data = incoming.sketch_data

    manually_changed = incoming.subtitle_text != old_subtitle
    override = incoming.subtitle_overridden or (
        manually_changed and incoming.subtitle_text != scene.narration_text
    )
    if narration_changed and not override:
        shot.subtitle_text = scene.narration_text
        shot.subtitle_source_revision = scene.revision
        shot.subtitle_overridden = False
    else:
        shot.subtitle_text = incoming.subtitle_text
        shot.subtitle_overridden = override
        if not override:
            shot.subtitle_source_revision = scene.revision

    if incoming.selected_media_version_id:
        selected_version = next(
            (
                item
                for item in shot.media_versions
                if item.id == incoming.selected_media_version_id
            ),
            None,
        )
        if not selected_version:
            raise HTTPException(status_code=422, detail="选中的媒体版本不属于当前镜头")
        for item in shot.media_versions:
            item.is_selected = item.id == selected_version.id
        shot.selected_media_version_id = selected_version.id
        shot.asset_id = selected_version.asset_id
        shot.visual_mode = "image" if selected_version.kind == "generated_image" else "video"
    else:
        for item in shot.media_versions:
            item.is_selected = False
        shot.selected_media_version_id = None
    shot.revision = max((shot.revision or 0) + 1, incoming.revision + 1)


async def save_workspace(
    db: AsyncSession,
    project: Project,
    user: User,
    request: WorkspaceSave,
) -> Project:
    script = project.script
    composition = project.composition
    if request.expected_revision != script.revision:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "项目已在其他页面更新，请先处理版本冲突",
                "client_revision": request.expected_revision,
                "server_revision": script.revision,
            },
        )
    document = request.document
    settings = document.settings
    scenes = document.storyboard.scenes
    if document.id != script.id:
        raise HTTPException(status_code=422, detail="不能替换项目绑定的项目文档")
    if document.revision != request.expected_revision:
        raise HTTPException(status_code=422, detail="项目文档版本与预期版本不一致")

    segments = await _validate_asset_references(db, user.id, scenes)
    await _link_used_assets(db, project, user.id, scenes)

    if request.project:
        for field, value in request.project.model_dump(exclude_unset=True).items():
            setattr(project, field, value)
    script.title = settings.title
    script.summary = settings.summary
    script.status = settings.status
    script.target_duration_seconds = settings.target_duration_seconds
    script.source_type = settings.source_type
    script.visual_config = settings.visual_config

    existing_scenes = {item.id: item for item in script.units}
    kept_scene_ids: set[str] = set()
    ordered_scenes: list[ScriptUnit] = []
    for scene_data in sorted(scenes, key=lambda item: item.index):
        if scene_data.id:
            scene = existing_scenes.get(scene_data.id)
            if not scene:
                raise HTTPException(status_code=422, detail="场景不属于当前项目")
            kept_scene_ids.add(scene.id)
        else:
            # SQLAlchemy column defaults are applied during INSERT.  A newly
            # constructed scene is used immediately below, before the first
            # flush, so initialise the relationship and revision explicitly.
            scene = ScriptUnit(script=script, revision=0, shots=[])
            db.add(scene)
        narration_changed = scene.narration_text != scene_data.narration_text
        scene.index = len(ordered_scenes)
        scene.outline = scene_data.outline
        scene.narration_text = scene_data.narration_text
        scene.intent = scene_data.intent
        scene.status = scene_data.status
        scene.estimated_duration_ms = scene_data.estimated_duration_ms
        scene.notes = scene_data.notes
        if narration_changed:
            scene.revision = (scene.revision or 0) + 1

        existing_shots = {item.id: item for item in scene.shots}
        kept_shot_ids: set[str] = set()
        ordered_shots: list[Shot] = []
        for shot_data in sorted(scene_data.shots, key=lambda item: item.index):
            if shot_data.id:
                shot = existing_shots.get(shot_data.id)
                if not shot:
                    raise HTTPException(status_code=422, detail="镜头不属于当前场景")
                kept_shot_ids.add(shot.id)
            else:
                # The new shot is also inspected before INSERT.  Keep its
                # collection relationships loaded and its optimistic revision
                # numeric from the start.
                shot = Shot(unit=scene, revision=0, candidates=[], media_versions=[])
                shot.subtitle_text = scene.narration_text
                shot.subtitle_source_revision = scene.revision
                if not shot_data.subtitle_overridden and not shot_data.subtitle_text:
                    shot_data.subtitle_text = scene.narration_text
                db.add(shot)
            shot_data.index = len(ordered_shots)
            _apply_shot(
                shot,
                shot_data,
                scene,
                narration_changed,
                segments.get(shot_data.segment_id or ""),
            )
            ordered_shots.append(shot)
        omitted_shot_ids = set(existing_shots) - kept_shot_ids
        if omitted_shot_ids:
            raise HTTPException(
                status_code=422,
                detail="删除镜头必须使用带确认和撤销令牌的删除接口",
            )
        scene.shots = ordered_shots
        scene.estimated_duration_ms = sum(shot.duration_ms for shot in ordered_shots)
        ordered_scenes.append(scene)

    omitted_scene_ids = set(existing_scenes) - kept_scene_ids
    if omitted_scene_ids:
        raise HTTPException(
            status_code=422,
            detail="删除场景必须使用带确认和撤销令牌的删除接口",
        )
    script.units = ordered_scenes
    script.estimated_duration_seconds = round(
        sum(scene.estimated_duration_ms for scene in ordered_scenes) / 1000
    )

    composition.aspect_ratio = settings.aspect_ratio
    composition.resolution = settings.resolution
    composition.fps = settings.fps
    composition.visual_settings = settings.visual_settings
    composition.global_audio = settings.global_audio
    composition.global_overlays = settings.global_overlays
    composition.timeline = document.timeline.model_dump(mode="json")
    composition.visual_layers = document.visual_layers.model_dump(mode="json")
    composition.global_scopes = document.global_scopes.model_dump(mode="json")
    composition.workflow_graph = document.workflow_graph.model_dump(mode="json")
    composition.render_settings = document.render_settings
    if document.current_render_asset_id:
        output = await db.get(Asset, document.current_render_asset_id)
        if not output or output.owner_id != user.id:
            raise HTTPException(status_code=422, detail="当前主成片素材不存在")
        composition.current_render_asset_id = output.id
        project.master_output_asset_id = output.id
    else:
        composition.current_render_asset_id = None
        project.master_output_asset_id = None

    script.revision += 1
    composition.revision = script.revision
    project.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await record_revision(db, project, user.id, request.reason)
    await db.flush()
    return project


def _undo_payload_scene(scene: ScriptUnit) -> dict:
    return scene_document(scene).model_dump(mode="json")


def _undo_payload_shot(shot: Shot) -> dict:
    return shot_document(shot, shot.unit.revision).model_dump(mode="json")


async def delete_scene(
    db: AsyncSession,
    project: Project,
    user: User,
    scene_id: str,
    expected_revision: int,
) -> ProjectUndoToken:
    if project.script.revision != expected_revision:
        raise HTTPException(status_code=409, detail="项目版本已变化，请刷新后重试")
    scene = next((item for item in project.script.units if item.id == scene_id), None)
    if not scene:
        raise HTTPException(status_code=404, detail="场景不存在")
    payload = _undo_payload_scene(scene)
    await db.delete(scene)
    remaining = [item for item in project.script.units if item.id != scene_id]
    project.script.units = remaining
    for index, item in enumerate(remaining):
        item.index = index
    project.script.revision += 1
    project.composition.revision = project.script.revision
    token = ProjectUndoToken(
        project_id=project.id,
        operation="delete_scene",
        payload=payload,
        base_revision=project.script.revision,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    db.add(token)
    await db.flush()
    await record_revision(
        db, project, user.id, "delete_scene", {"scene_id": scene_id, "undo_token": token.id}
    )
    await db.flush()
    return token


async def delete_shot(
    db: AsyncSession,
    project: Project,
    user: User,
    shot_id: str,
    expected_revision: int,
) -> ProjectUndoToken:
    if project.script.revision != expected_revision:
        raise HTTPException(status_code=409, detail="项目版本已变化，请刷新后重试")
    shot = next(
        (shot for scene in project.script.units for shot in scene.shots if shot.id == shot_id),
        None,
    )
    if not shot:
        raise HTTPException(status_code=404, detail="镜头不存在")
    payload = {"scene_id": shot.unit_id, "shot": _undo_payload_shot(shot)}
    scene = shot.unit
    await db.delete(shot)
    remaining = [item for item in scene.shots if item.id != shot_id]
    scene.shots = remaining
    for index, item in enumerate(remaining):
        item.index = index
    scene.estimated_duration_ms = sum(item.duration_ms for item in remaining)
    project.script.revision += 1
    project.composition.revision = project.script.revision
    token = ProjectUndoToken(
        project_id=project.id,
        operation="delete_shot",
        payload=payload,
        base_revision=project.script.revision,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    db.add(token)
    await db.flush()
    await record_revision(
        db, project, user.id, "delete_shot", {"shot_id": shot_id, "undo_token": token.id}
    )
    await db.flush()
    return token


def _restore_shot(scene: ScriptUnit, data: ShotDocument) -> Shot:
    shot = Shot(
        id=data.id,
        unit=scene,
        index=data.index,
        description=data.description,
        status=data.status,
        visual_mode=data.visual_mode,
        asset_id=data.asset_id,
        segment_id=data.segment_id,
        source_start_ms=data.source_start_ms,
        source_end_ms=data.source_end_ms,
        duration_ms=data.duration_ms,
        locked=data.locked,
        transform=data.transform,
        adjust=data.adjust,
        audio_settings=data.audio_settings,
        subtitle_settings=data.subtitle_settings,
        transition=data.transition,
        motion=data.motion,
        subtitle_text=data.subtitle_text,
        subtitle_overridden=data.subtitle_overridden,
        subtitle_source_revision=data.subtitle_source_revision,
        notes=data.notes,
        sketch_data=data.sketch_data,
        revision=data.revision,
    )
    for item in data.candidates:
        shot.candidates.append(
            Candidate(
                id=item.id,
                segment_id=item.segment_id,
                title=item.title,
                source=item.source,
                range_start_ms=item.range_start_ms,
                range_end_ms=item.range_end_ms,
                score=item.score,
                reason=item.reason,
                low_confidence=item.low_confidence,
            )
        )
    for item in data.media_versions:
        shot.media_versions.append(
            ShotMediaVersion(
                id=item.id,
                asset_id=item.asset_id,
                job_id=item.job_id,
                parent_version_id=item.parent_version_id,
                kind=item.kind,
                operation=item.operation,
                parameters=item.parameters,
                status=item.status,
                is_selected=item.is_selected,
                created_at=item.created_at,
            )
        )
    return shot


async def undo_mutation(
    db: AsyncSession,
    project: Project,
    user: User,
    token_id: str,
) -> None:
    token = await db.get(ProjectUndoToken, token_id, with_for_update=True)
    now = datetime.now(timezone.utc)
    if not token or token.project_id != project.id:
        raise HTTPException(status_code=404, detail="撤销操作不存在")
    if token.used_at:
        raise HTTPException(status_code=409, detail="该撤销操作已经使用")
    if token.expires_at <= now:
        raise HTTPException(status_code=410, detail="撤销操作已过期，可从版本历史恢复")
    if project.script.revision != token.base_revision:
        raise HTTPException(status_code=409, detail="项目已继续编辑，不能直接撤销；请从版本历史恢复")

    if token.operation == "delete_shot":
        scene = next(
            (item for item in project.script.units if item.id == token.payload["scene_id"]),
            None,
        )
        if not scene:
            raise HTTPException(status_code=409, detail="原场景已不存在，不能自动恢复镜头")
        data = ShotDocument.model_validate(token.payload["shot"])
        restored_shot = _restore_shot(scene, data)
        scene.shots.append(restored_shot)
        scene.shots.sort(key=lambda item: item.index)
        for index, shot in enumerate(scene.shots):
            shot.index = index
        scene.estimated_duration_ms = sum(item.duration_ms for item in scene.shots)
        await db.flush()
        restored_shot.selected_media_version_id = data.selected_media_version_id
    elif token.operation == "delete_scene":
        data = SceneDocument.model_validate(token.payload)
        scene = ScriptUnit(
            id=data.id,
            script=project.script,
            index=data.index,
            outline=data.outline,
            narration_text=data.narration_text,
            intent=data.intent,
            status=data.status,
            estimated_duration_ms=data.estimated_duration_ms,
            notes=data.notes,
            revision=data.revision,
        )
        restored_pairs: list[tuple[Shot, ShotDocument]] = []
        for shot_data in data.shots:
            restored = _restore_shot(scene, shot_data)
            scene.shots.append(restored)
            restored_pairs.append((restored, shot_data))
        project.script.units.append(scene)
        project.script.units.sort(key=lambda item: item.index)
        for index, item in enumerate(project.script.units):
            item.index = index
        await db.flush()
        for restored, shot_data in restored_pairs:
            restored.selected_media_version_id = shot_data.selected_media_version_id
    else:
        raise HTTPException(status_code=409, detail="不支持该撤销操作")

    token.used_at = now
    project.script.revision += 1
    project.composition.revision = project.script.revision
    await db.flush()
    await record_revision(
        db, project, user.id, "undo_delete", {"undo_token": token.id, "operation": token.operation}
    )
    await db.flush()
