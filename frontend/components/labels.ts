export const CATEGORY_LABEL: Record<string, string> = {
  ROAD_INFRASTRUCTURE: "Roads & potholes",
  WATER_SUPPLY: "Water supply / leakage",
  SANITATION: "Sanitation & garbage",
  DRAINAGE: "Drainage",
  STREETLIGHT: "Streetlight",
  PUBLIC_INFRASTRUCTURE: "Public infrastructure",
  OTHER: "Other",
};

export const STATUS_LABEL: Record<string, string> = {
  SUBMITTED: "Submitted",
  UNDER_REVIEW: "Under review",
  ASSIGNED: "Assigned",
  IN_PROGRESS: "In progress",
  ON_HOLD: "On hold",
  RESOLVED_AWAITING_VERIFICATION: "Resolved – awaiting verification",
  VERIFIED_RESOLVED: "Verified resolved",
  REJECTED: "Rejected",
  REOPENED: "Reopened",
};

export const STATUS_STYLE: Record<string, string> = {
  SUBMITTED: "bg-slate-100 text-slate-700 ring-slate-300",
  UNDER_REVIEW: "bg-blue-50 text-blue-800 ring-blue-200",
  ASSIGNED: "bg-navy-50 text-navy-800 ring-navy-200",
  IN_PROGRESS: "bg-sky-50 text-sky-800 ring-sky-200",
  ON_HOLD: "bg-amber-50 text-amber-800 ring-amber-200",
  RESOLVED_AWAITING_VERIFICATION: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  VERIFIED_RESOLVED: "bg-green-50 text-green-800 ring-green-300",
  REJECTED: "bg-red-50 text-red-800 ring-red-200",
  REOPENED: "bg-orange-50 text-orange-800 ring-orange-200",
};

export const PRIORITY_STYLE: Record<string, string> = {
  CRITICAL: "bg-red-600 text-white ring-red-600",
  HIGH: "bg-orange-100 text-orange-900 ring-orange-300",
  MEDIUM: "bg-yellow-50 text-yellow-900 ring-yellow-300",
  LOW: "bg-slate-50 text-slate-700 ring-slate-300",
};

export const ROUTING_LABEL: Record<string, string> = {
  ROUTED: "Routed",
  PENDING_REVIEW: "Administrative review required",
  UNROUTED: "No eligible department configured",
};

export const ROLE_LABEL: Record<string, string> = {
  CITIZEN: "Citizen",
  OFFICER: "Officer",
  DEPARTMENT_ADMIN: "Department administrator",
  SYSTEM_ADMIN: "Main administrator",
};

export const JURISDICTION_TYPE_LABEL: Record<string, string> = {
  STATE: "State", DISTRICT: "District", SUBDIVISION: "Sub-division", TALUK: "Taluk", MANDAL: "Mandal",
  MUNICIPAL_CORPORATION: "Municipal corporation", MUNICIPALITY: "Municipality", GRAM_PANCHAYAT: "Gram panchayat",
  WARD: "Ward", VILLAGE: "Village", ZONE: "Zone", OTHER: "Other",
};

export const ISSUE_STATUS_LABEL: Record<string, string> = {
  DRAFT: "Draft", VERIFIED: "Verified – awaiting publication", PUBLISHED: "Published", UNPUBLISHED: "Unpublished",
};

export const ISSUE_PROGRESS_LABEL: Record<string, string> = {
  REPORTED: "Reported", IN_PROGRESS: "Work in progress", RESOLVED: "Resolved",
};

export const REASON_LABEL: Record<string, string> = {
  LOCATION_UNCERTAIN: "Location uncertain",
  NO_JURISDICTION_CONFIGURED: "No jurisdictions configured",
  OUTSIDE_JURISDICTION: "Outside configured jurisdictions",
  NO_RESPONSIBILITY: "No department responsible",
  MULTIPLE_DEPARTMENTS: "Multiple departments responsible",
  DEPARTMENT_NOT_ACTIVE_HERE: "Department not active here",
  OVERDUE: "Overdue",
  MANUAL: "Raised manually",
};

/** Relative time like "in 3 days" / "2 days ago" for deadlines. */
export function relDays(iso?: string | null): { days: number; overdue: boolean } | null {
  if (!iso) return null;
  const ms = new Date(iso).getTime() - Date.now();
  return { days: Math.round(Math.abs(ms) / 86400000), overdue: ms < 0 };
}

export const FACTOR_LABEL: Record<string, string> = {
  severity: "Physical severity (S)",
  safety_risk: "Safety risk (R)",
  location_sensitivity: "Location sensitivity (L)",
  public_exposure: "Public exposure (E)",
  duration: "Reported duration (D)",
};

export function fmtDate(iso?: string | null, withTime = true): string {
  if (!iso) return "—";
  const d = new Date(iso);
  const opts: Intl.DateTimeFormatOptions = withTime
    ? { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }
    : { day: "2-digit", month: "short", year: "numeric" };
  return d.toLocaleString("en-IN", opts);
}

export function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}
