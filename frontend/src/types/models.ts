// ──────────────────────────────────────────────
// OpenVMA - 数据模型类型定义
// 对应后端 Schema 与设计文档（02-详细设计 4.1~4.8）
// ──────────────────────────────────────────────

/* ── 认证相关 ── */

export interface UserMembership {
  id: string;
  name: string;
  rank: number;
}

export interface UserSubscription {
  id: string;
  membershipId: string;
  status: "active" | "internal" | "past_due" | "cancelled" | "expired";
  billingCycle: "monthly" | "yearly" | "permanent";
  currentPeriodStart: string;
  currentPeriodEnd?: string;
  autoRenew: boolean;
  cancelAtPeriodEnd: boolean;
  provider: string;
}

export interface User {
  id: string;
  email: string;
  name: string;
  avatar?: string;
  initial: string;
  createdAt: string;
  notifyAssetProcessing: boolean;
  notifyScriptGeneration: boolean;
  notifyMarketing: boolean;
  membership?: UserMembership;
  subscription?: UserSubscription;
}

export interface AuthTokens {
  accessToken: string;
  refreshToken: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  name: string;
}

export interface AuthResponse {
  user: User;
  tokens: AuthTokens;
}

/* ── 会员与用量 ── */

export interface Membership {
  id: string;
  name: string;
  rank: number;
  billingCycle: "monthly" | "yearly";
  processingMinutes: number;
  paymentMethod?: string;
}

export interface Usage {
  processingMinutesUsed: number;
  processingMinutesTotal: number;
  aiImageCount: number;
  aiImageLimit: number;
  aiVideoCount: number;
  aiVideoLimit: number;
  storageUsed: number;
  storageLimit: number;
}

/* ── 缩略图变体 ── */

export type ThumbnailVariant =
  | "stage"
  | "robot"
  | "interview"
  | "crowd"
  | "lights"
  | "hall"
  | "speaker";

/* ── 项目 ── */

export type ProjectStatus =
  | "处理中"
  | "全部可搜索"
  | "素材已就绪"
  | "等待上传"
  | "脚本编辑中"
  | "脚本已导入"
  | "AI 初剪生成中"
  | "AI 初剪可编辑";

export interface Project {
  id: string;
  name: string;
  initial: string;
  type: string;
  description: string;
  updatedAt: string;
  status: ProjectStatus;
  assetCount: number;
  clipCount: number;
  scriptCount: number;
  variant: ThumbnailVariant;
  members: string[];
  currentUserRole: "owner" | "editor" | "viewer";
  isNew?: boolean;
  sourceScriptId?: string;
  visualStyle?: string;
  aspectRatio?: string;
  aiShotCount?: number;
}

/* ── 素材 ── */

export type AssetStatus = "处理中" | "处理完成" | "AI 处理中" | "处理失败" | "失败";

export interface Asset {
  id: string;
  projectId: string;
  importedFromAssetId?: string;
  name: string;
  mediaType: "video" | "audio";
  hasAudio: boolean;
  duration: string;
  status: AssetStatus;
  source: string;
  variant: ThumbnailVariant;
  mediaUrl?: string;
  thumbnailUrl?: string;
  fileSizeMb?: number;
  resolution?: string;
  fps?: number;
  codec?: string;
  audioCodec?: string;
  sampleRate?: number;
  channels?: number;
  bitrate?: number;
  transcript?: string;
  ocrText?: string;
  tags?: string[];
  matchField?: "name" | "tag" | "transcript" | "ocr" | "clip_title" | "clip_transcript" | "clip_ocr";
  matchExcerpt?: string;
  matchedClipId?: string;
  uploadedAt: string;
  clips: Clip[];
}

/* ── 片段 ── */

export type SceneType =
  | "全景"
  | "中景"
  | "近景"
  | "特写"
  | "舞台全景"
  | "观众席"
  | "产品展示"
  | "采访"
  | "空镜"
  | null;

export type ShotType =
  | "固定"
  | "推拉"
  | "摇移"
  | "跟拍"
  | "航拍"
  | "手持"
  | null;

export type CameraMotion =
  | "静止"
  | "缓慢推进"
  | "快速摇移"
  | "稳定器跟拍"
  | "升降"
  | "变焦"
  | null;

export interface Clip {
  id: string;
  assetId: string;
  startTime: number;
  endTime: number;
  duration: number;
  title: string;
  transcriptSegment?: string;
  ocrSegment?: string;
  sceneType?: SceneType;
  shotType?: ShotType;
  cameraMotion?: CameraMotion;
  persons?: string[];
  objects?: string[];
  thumbnailPath?: string;
  thumbnailUrl?: string;
  variant: ThumbnailVariant;
  qualityScore?: number;
  /** 兼容字段：格式化的时间范围字符串 */
  range?: string;
  tags?: string[];
  transcript?: string;
}

/* ── 脚本 ── */

export type ScriptStatus =
  | "编辑中"
  | "待匹配"
  | "待确认"
  | "已完成"
  | "初剪生成中"
  | "初剪可编辑";

export type ScriptFormat = "横屏 16:9" | "竖屏 9:16" | "方形 1:1";

export type ScriptSourceType = "blank" | "paste" | "spreadsheet" | "ai";

export interface Script {
  id: string;
  projectId: string;
  title: string;
  summary: string;
  status: ScriptStatus;
  updatedAt: string;
  duration: string;
  unitCount: number;
  matchedCount: number;
  progress: number;
  variant: ThumbnailVariant;
  format: ScriptFormat;
  visualConfig?: VisualConfig;
  needsInitialSave?: boolean;
  sourceType?: ScriptSourceType;
  isSnapshot?: boolean;
  parentScriptId?: string;
  units?: ScriptUnit[];
}

export type ScriptUnitStatus = "已选择" | "有候选" | "待确认" | "待编辑";

export interface ScriptUnit {
  id: string;
  scriptId?: string;
  sourceUnitId?: string;
  index: number;
  outline: string;
  text: string;
  intent: string;
  status: ScriptUnitStatus;
  selectedClipId: string | null;
  duration: number;
  notes: string;
  candidates: Candidate[];
  shots: Shot[];
}

export type ShotStatus = "已选择" | "待编辑" | "待确认";

export type VisualMode = "recommend" | "image" | "video" | "sketch" | null;

export interface Shot {
  id: string;
  unitId?: string;
  sourceShotId?: string;
  index?: number;
  description: string;
  status: ShotStatus;
  selectedClipId: string | null;
  visualMode: VisualMode;
  duration: number;
  notes: string;
  generatedImagePath?: string;
  generatedVideoPath?: string;
  generatedEffectVideoPath?: string;
  generations: ShotGeneration[];
  candidates: Candidate[];
}

export interface ShotGeneration {
  id: string;
  shotId: string;
  jobId?: string;
  kind: "image" | "video" | "effect";
  storagePath: string;
  mediaUrl?: string;
  prompt: string;
  isSelected: boolean;
  createdAt: string;
}

export interface Candidate {
  id: string;
  shotId?: string;
  unitId?: string;
  clipId?: string;
  title: string;
  source: string;
  rangeStart?: number;
  rangeEnd?: number;
  score: number;
  reason: string;
  variant: ThumbnailVariant;
  lowConfidence?: boolean;
  thumbnailUrl?: string;
  /** 兼容字段：格式化的时间范围字符串 */
  range?: string;
}

/* ── 异步任务 ── */

export type JobStatus = "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "PAUSED" | "CANCELLED";

export type JobType =
  | "素材处理"
  | "AI 脚本生成"
  | "AI 分镜完善"
  | "镜头匹配"
  | "AI 生图分镜"
  | "分镜图 AI 生视频"
  | "示意图特效视频"
  | "AI 初剪生成"
  | "导出";

export interface JobLog {
  message: string;
  timestamp: string;
  level?: "info" | "warn" | "error";
}

export interface Job {
  id: string;
  projectId: string;
  name: string;
  type: JobType;
  status: JobStatus;
  stage: string;
  stages: string[];
  stageIndex: number;
  progress: number;
  detail: string;
  eta: string;
  logs: JobLog[];
  result?: string;
  resultDetail?: string;
  resultUrl?: string;
  isSimulated: boolean;
  createdAt: string;
}

/* ── 视觉一致性配置 ── */

export type StylePreset = "brand-tech" | "cinematic" | "documentary" | "illustration";

export type AspectRatio = "16:9" | "9:16" | "1:1" | "4:3";

export type Palette = "冷灰蓝" | "自然中性" | "暖金色" | "高饱和撞色";

export type CameraRhythm = "稳定推进" | "舒缓留白" | "快速切换" | "手持纪实";

export interface VisualConfig {
  stylePreset: StylePreset;
  aspectRatio: AspectRatio;
  palette: Palette;
  cameraRhythm: CameraRhythm;
  consistencyEnabled: boolean;
  generationPolicy: string;
  references: {
    characters: Reference[];
    objects: Reference[];
    spaces: Reference[];
  };
}

/* ── 统一素材引用 ── */

export interface Reference {
  id: string;
  category?: "characters" | "objects" | "spaces";
  assetId?: string;
  clipId?: string;
  name: string;
  detail: string;
  variant: ThumbnailVariant;
  locked: boolean;
}

/* ── API 通用响应 ── */

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page?: number;
  pageSize?: number;
}

export interface ApiError {
  detail: string;
  code?: string;
}
