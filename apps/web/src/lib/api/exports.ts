import { apiClient } from "./client";

async function downloadBlob(url: string, filename: string): Promise<void> {
  const { data } = await apiClient.get<Blob>(url, { responseType: "blob" });
  const objectUrl = URL.createObjectURL(data);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(objectUrl);
}

export const exportsApi = {
  async roadmapMarkdown(roadmapId: string): Promise<void> {
    await downloadBlob(`/api/v1/exports/roadmap/${roadmapId}/markdown`, "roadmap.md");
  },

  async roadmapIcs(roadmapId: string): Promise<void> {
    await downloadBlob(`/api/v1/exports/roadmap/${roadmapId}/ics`, "roadmap.ics");
  },
};
