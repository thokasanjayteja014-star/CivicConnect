export type Role = "CITIZEN" | "OFFICER" | "DEPARTMENT_ADMIN" | "SYSTEM_ADMIN";

export const CATEGORIES = [
  "ROAD_INFRASTRUCTURE", "WATER_SUPPLY", "SANITATION", "DRAINAGE", "STREETLIGHT", "PUBLIC_INFRASTRUCTURE", "OTHER",
] as const;
export type Category = (typeof CATEGORIES)[number];

export const STATUSES = [
  "SUBMITTED", "UNDER_REVIEW", "ASSIGNED", "IN_PROGRESS", "ON_HOLD", "RESOLVED_AWAITING_VERIFICATION",
  "VERIFIED_RESOLVED", "REJECTED", "REOPENED",
] as const;
export type ComplaintStatus = (typeof STATUSES)[number];

export type PriorityLevel = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type RoutingStatus = "ROUTED" | "PENDING_REVIEW" | "UNROUTED";

export interface Me {
  id: string;
  full_name: string;
  email: string;
  phone: string | null;
  role: Role;
  account_status: string;
  notify_email: boolean;
  notify_sms: boolean;
  notify_push: boolean;
  preferred_language: "en" | "hi" | "kn" | "te";
  department_id: string | null;
  department_name: string | null;
  officer_id: string | null;
  unit_id: string | null;
  jurisdiction_name: string | null;
  environment: "production" | "demo";
  permissions: string[];
}

export interface ComplaintListItem {
  complaint_id: string;
  reference_id: string;
  title: string;
  category: Category;
  status: ComplaintStatus;
  priority_score: number | null;
  priority_level: PriorityLevel | null;
  priority_assessment_status: string;
  needs_prompt_review: boolean;
  routing_status: RoutingStatus;
  department: { id: string; name: string; is_prototype: boolean } | null;
  location: { latitude: number; longitude: number; landmark?: string | null; address_text?: string | null };
  assigned_officer: { officer_id: string; designation: string; full_name?: string } | null;
  assignment_accepted?: boolean;
  jurisdiction?: { id: string; name: string } | null;
  due_at?: string | null;
  overdue?: boolean;
  escalated?: number | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface MediaItem {
  media_id: string;
  media_type: "IMAGE" | "AUDIO" | "VIDEO";
  mime_type: string;
  file_size_bytes: number;
  duration_seconds: number | null;
  original_filename: string | null;
  uploaded_at: string;
}

export interface Factor { value: number | null; source: string; explanation: string; method: string }

export interface ComplaintDetail extends ComplaintListItem {
  original_description: string | null;
  description: string;
  occurred_at: string | null;
  additional_details: string | null;
  location: ComplaintListItem["location"] & { accuracy_meters: number | null; location_source: string };
  citizen_observations: Record<string, string | null>;
  media: MediaItem[];
  priority: {
    priority_score: number | null; priority_level: PriorityLevel | null; priority_assessment_status: string;
    needs_prompt_review: boolean; factors: Record<string, Factor> | null; weights: Record<string, number> | null;
    review_reasons: string[]; rubric_version: string | null; assessed_by: string | null; assessed_at: string | null; disclaimer: string;
  };
  routing: {
    routing_status: RoutingStatus; department: ComplaintListItem["department"]; message: string | null; explanation: string | null;
    requires_admin_review: boolean; decided_at: string | null; reason_code?: string; rule_version?: string;
    jurisdiction?: { id: string; name: string; is_prototype: boolean } | null; candidates?: any; manually_reviewed?: boolean;
  };
  timeline: Array<{ type: string; previous_status?: string | null; new_status?: string; actor_role: string; remarks: string | null;
    created_at: string; visibility?: string; author_name?: string }>;
  resolution_evidence: Array<{ evidence_id: string; description: string | null; created_at: string; media: MediaItem }>;
  verification_decisions: Array<{ decision: string; reason: string; created_at: string; citizen_responded: boolean }>;
  feedback: Array<{ feedback_id: string; feedback_type: string; remarks: string | null; review_status: string;
    reviewed_at: string | null; decision_reason: string | null; created_at: string }>;
  ai_analysis: any | null;
  ai_review_required: boolean;
  allow_public_display: boolean;
  publication_status: string;
  public_summary: string | null;
  related: any[];
  workflow_notice: string;
  permitted_actions?: {
    status_targets: ComplaintStatus[]; can_assign: boolean; can_reassign: boolean; can_upload_evidence: boolean;
    has_evidence: boolean; can_verify: boolean; can_decide_reopening: boolean; can_accept?: boolean; can_escalate?: boolean;
  };
  assignments?: any[];
  routing_history?: any[];
  citizen_actions?: { can_edit: boolean; can_confirm_resolution: boolean; can_request_reopen: boolean };
  escalations?: any[];
  jurisdiction_path?: string | null;
  unit?: { id: string; department: string; jurisdiction: string } | null;
}
