import type { MetadataRoute } from "next";

/**
 * Web App Manifest (PWA, §17). Served at /manifest.webmanifest by Next's
 * metadata route. The SVG icon is declared with sizes "any" + a maskable purpose
 * so modern browsers can install the app to the home screen / dock.
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Career Roadmap AI",
    short_name: "Roadmap AI",
    description: "Your career, designed and tracked like an engineering project.",
    start_url: "/dashboard",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#F7F2E8",
    theme_color: "#134E3A",
    categories: ["education", "productivity", "business"],
    icons: [
      {
        src: "/icon.svg",
        sizes: "any",
        type: "image/svg+xml",
        purpose: "any",
      },
      {
        src: "/icon.svg",
        sizes: "any",
        type: "image/svg+xml",
        purpose: "maskable",
      },
    ],
  };
}
