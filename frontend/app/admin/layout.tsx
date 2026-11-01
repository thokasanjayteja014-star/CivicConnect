import { PortalLayout } from "@/components/PortalLayout";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return <PortalLayout roles={["SYSTEM_ADMIN"]}>{children}</PortalLayout>;
}
