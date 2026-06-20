import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Providers } from "@/providers";
import { ConditionalShell } from "@/components/layout/conditional-shell";
import { ServiceWorkerRegister } from "@/components/pwa/service-worker-register";
import "./globals.css";

const geist = Geist({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const geistMono = Geist_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Career Roadmap AI",
  description: "Your career, designed and tracked like an engineering project.",
  manifest: "/manifest.webmanifest",
  applicationName: "Career Roadmap AI",
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "Roadmap AI",
  },
  icons: {
    icon: "/icon.svg",
    apple: "/icon.svg",
  },
};

export const viewport: Viewport = {
  themeColor: "#134E3A",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning className="scroll-smooth">
      <body className={`${geist.variable} ${geistMono.variable} antialiased`}>
        <Providers>
          <ConditionalShell>
            {children}
          </ConditionalShell>
          <ServiceWorkerRegister />
        </Providers>
      </body>
    </html>
  );
}