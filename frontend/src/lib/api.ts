/** API client for CodeABC backend. */

const BASE = "/api";

function getHeaders(): HeadersInit {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  // BYOK: attach user's API key if configured
  const apiKey = localStorage.getItem("codeabc_api_key");
  if (apiKey) {
    headers["x-api-key"] = apiKey;
  }
  return headers;
}

export interface FileInfo {
  path: string;
  size: number;
  language: string;
}

export interface ProjectMeta {
  id: string;
  name: string;
  total_files: number;
  files: FileInfo[];
}

export interface Annotation {
  line_start: number;
  line_end: number;
  annotation: string;
}

export interface ProjectOverview {
  summary: string;
  description: string;
  files: { path: string; role: string; importance: string }[];
  how_to_run: string[];
  quick_tips: string[];
}

/** Fetch project metadata by ID (for page refresh). */
export async function getProject(projectId: string): Promise<ProjectMeta> {
  const res = await fetch(`${BASE}/project/${projectId}`, {
    headers: getHeaders(),
  });
  if (!res.ok) throw new Error("Project not found");
  return res.json();
}

/** Upload local files to create a project. */
export async function uploadProject(
  files: { path: string; content: string }[],
  projectName: string
): Promise<ProjectMeta> {
  const res = await fetch(`${BASE}/project/upload`, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({ files, project_name: projectName }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Upload failed");
  }
  return res.json();
}

/** Clone a GitHub repo to create a project. */
export async function cloneGitHub(url: string): Promise<ProjectMeta> {
  const res = await fetch(`${BASE}/project/github`, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({ url }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Clone failed");
  }
  return res.json();
}

/** Stream project overview via SSE. Calls onChunk for each text chunk,
 *  and onResult when the final parsed JSON arrives. */
export async function streamOverview(
  projectId: string,
  onChunk: (text: string) => void,
  onResult: (overview: ProjectOverview) => void,
  onError: (err: string) => void
) {
  const apiKey = localStorage.getItem("codeabc_api_key");
  const headers: Record<string, string> = {};
  if (apiKey) headers["x-api-key"] = apiKey;

  const res = await fetch(`${BASE}/project/${projectId}/overview`, { headers });
  if (!res.ok || !res.body) {
    if (res.status === 429) {
      const err = await res.json().catch(() => ({ detail: "请求过于频繁" }));
      onError(err.detail || "今日免费额度已用完，请配置 API Key");
    } else {
      onError("Failed to load overview");
    }
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // parse SSE lines
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const data = line.slice(6);
      if (data === "[DONE]") return;

      try {
        const parsed = JSON.parse(data);
        if (parsed.chunk) onChunk(parsed.chunk);
        if (parsed.result) onResult(parsed.result);
        if (parsed.raw) onChunk(parsed.raw);
      } catch {
        // ignore parse errors in stream
      }
    }
  }
}

/** Get file content. */
export async function getFileContent(
  projectId: string,
  filePath: string
): Promise<{ path: string; language: string; content: string }> {
  const res = await fetch(
    `${BASE}/project/${projectId}/file/${encodeURIComponent(filePath)}`,
    { headers: getHeaders() }
  );
  if (!res.ok) throw new Error("File not found");
  return res.json();
}

/** Get annotations for a file. */
export async function getAnnotations(
  projectId: string,
  filePath: string
): Promise<{ annotations: Annotation[] }> {
  const res = await fetch(
    `${BASE}/project/${projectId}/file/${encodeURIComponent(filePath)}/annotations`,
    { headers: getHeaders() }
  );
  if (!res.ok) {
    if (res.status === 429) {
      const err = await res.json().catch(() => ({ detail: "请求过于频繁" }));
      throw new Error(err.detail || "今日免费额度已用完，请配置 API Key");
    }
    throw new Error("Failed to get annotations");
  }
  return res.json();
}
