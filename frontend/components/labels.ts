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
  ASSIGNED: "bg-indigo-50 text-indigo-800 ring-indigo-200",
  IN_PROGRESS: "bg-teal-50 text-teal-800 ring-teal-200",
  ON_HOLD: "bg-amber-50 text-amber-800 ring-amber-200",
  RESOLVED_AWAITING_VERIFICATION: "bg-lime-50 text-lime-800 ring-lime-200",
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
  OFFICER: "Department officer",
  DEPARTMENT_ADMIN: "Department admin",
  SYSTEM_ADMIN: "System admin",
};

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
  return withTime ? d.toLocaleString() : d.toLocaleDateString();
}

export function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}
