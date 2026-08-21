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

export interface LoginRequest { email: string; password: string }
export interface RegisterRequest { email: string; password: string; name: string }

export type ThumbnailVariant = "stage" | "robot" | "interview" | "crowd" | "lights" | "hall" | "speaker";

export type JobStatus = "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "PAUSED" | "CANCELLED";
export type JobType = string;

export interface JobLog {
  message: string;
  timestamp: string;
  level?: "info" | "warn" | "error";
}

export interface Job {
  id: string;
  projectId?: string;
  subjectType?: string;
  subjectId?: string;
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
  exportMetadata?: {
    format: string;
    resolution: string;
    aspectRatio: string;
  };
  isSimulated: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page?: number;
  pageSize?: number;
}

export interface ApiError {
  detail: unknown;
  code?: string;
}
