import { http } from "./client";

export interface ActivityHeartbeatResponse {
  activity_date: string;
  recorded: boolean;
  next_write_after_seconds: number;
}

export function heartbeat(): Promise<ActivityHeartbeatResponse> {
  return http.post<ActivityHeartbeatResponse>("/activity/heartbeat");
}
