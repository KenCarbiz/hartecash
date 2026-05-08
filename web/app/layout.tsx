import type { Metadata, Viewport } from "next";
import { AppShell } from "@/components/AppShell";
import { getCurrentUser } from "@/lib/api";
import "./globals.css";

export const metadata: Metadata = {
  title: "AutoAcquisition · Acquisitions",
  description: "Private-party vehicle acquisition for dealers",
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    title: "AutoAcquisition",
    capable: true,
    statusBarStyle: "default",
  },
  icons: {
    icon: [{ url: "/icon.svg", type: "image/svg+xml" }],
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // Stops iOS from auto-zooming form inputs <16px (forces layout reflow
  // mid-typing). We size inputs at 14px in tailwind; cap user zoom at 5x
  // so accessibility-zoom still works.
  maximumScale: 5,
  themeColor: "#0c2340",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const user = await getCurrentUser().catch(() => null);
  return (
    <html lang="en">
      <body>
        <AppShell user={user}>{children}</AppShell>
      </body>
    </html>
  );
}
