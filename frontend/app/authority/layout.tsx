import { PortalLayout } from "@/components/PortalLayout";

export default function AuthorityLayout({ children }: { children: React.ReactNode }) {
  return <PortalLayout roles={["OFFICER", "DEPARTMENT_ADMIN", "SYSTEM_ADMIN"]}>{children}</PortalLayout>;
}
