import type { Metadata } from "next";
import { AppShell } from "@/components/AppShell";
import { AuthProvider } from "@/components/AuthProvider";
import { I18nProvider } from "@/components/I18nProvider";
import "@/styles/globals.css";

export const metadata: Metadata = {
  title: "CivicConnect",
  description: "Report civic issues, track their resolution, and see how reported problems are being addressed.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        {/* Noto families render English, Telugu, Hindi and Kannada consistently. */}
        {/* eslint-disable-next-line @next/next/no-page-custom-font */}
        <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans:wght@400;500;600;700&family=Noto+Sans+Telugu:wght@400;500;600;700&family=Noto+Sans+Devanagari:wght@400;500;600;700&family=Noto+Sans+Kannada:wght@400;500;600;700&display=swap" />
      </head>
      <body>
        <I18nProvider>
          <AuthProvider>
            <AppShell>{children}</AppShell>
          </AuthProvider>
        </I18nProvider>
      </body>
    </html>
  );
}
