/** API client for CodeABC backend. */
import { tStatic } from "./i18n";

// On the web the frontend is served next to the API, so a relative "/api" is
// proxied straight through. The desktop build (Tauri) loads from a tauri://
// origin where a relative "/api" resolves to the app shell, not the backend —
// so there we default to the local CodeABC server on 127.0.0.1:8000. An
// explicit VITE_API_BASE always wins (e.g. to point the desktop app at a
// hosted backend).
function isDesktopShell(): boolean {
  if (typeof window === "undefined") return false;
  return (
    window.location.protocol === "tauri:" ||
    window.location.hostname === "tauri.localhost" ||
    "__TAURI_INTERNALS__" in window
  );
}

const BASE =
  import.meta.env.VITE_API_BASE ??
  (isDesktopShell() ? "http://127.0.0.1:8000/api" : "/api");

/** fetch wrapper that turns a network-level failure in the desktop shell into a
 *  clear "the backend isn't running" message instead of a raw "Failed to fetch". */
async function apiFetch(input: string, init?: RequestInit): Promise<Response> {
  try {
    return await window.fetch(input, init);
  } catch (e) {
    if (isDesktopShell()) {
      throw new Error(
        tStatic(
          "连不上本地 CodeABC 后端（127.0.0.1:8000）。请先在项目目录运行 python run.py 启动后端，再重试。",
          "Can't reach the local CodeABC backend (127.0.0.1:8000). Start it with `python run.py` in the project folder, then retry.",
        ),
      );
    }
    throw e;
  }
}

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

export interface Hotspot {
  path: string;
  language: string;
  fan_in: number;
  dependents: string[];
  reason: string;
}

export interface ArchitectureLayer {
  path: string;
  language: string;
  layer: number;
  reason: string;
}

export interface PackageDependency {
  package: string;
  depends_on: string[];
  depended_on_by: string[];
  fan_out: number;
  fan_in: number;
  reason: string;
}

export interface CouplingHotspot {
  path: string;
  language: string;
  fan_out: number;
  dependencies: string[];
  reason: string;
}

export interface BlastRadiusHotspot {
  path: string;
  language: string;
  blast_radius: number;
  direct_dependents: string[];
  reason: string;
}

export interface ImportCycle {
  files: string[];
  size: number;
  reason: string;
}

export interface OrphanModule {
  path: string;
  language: string;
  reason: string;
}

export interface ProjectHealth {
  total_code_files: number;
  total_directories: number;
  circular_dependency_groups: number;
  orphan_files: number;
  most_depended_on: string;
  most_depended_on_fan_in: number;
  widest_blast_radius_file: string;
  widest_blast_radius: number;
  notes: string[];
}

export interface ChurnHotspot {
  path: string;
  commits: number;
  lines_changed: number;
  authors: number;
  reason: string;
}

export interface CoChangeCoupling {
  file_a: string;
  file_b: string;
  co_changes: number;
  coupling: number;
  reason: string;
}

export interface RiskHotspot {
  path: string;
  fan_in: number;
  commits: number;
  score: number;
  reason: string;
}

export interface TestCoverageFile {
  path: string;
  language: string;
  fan_in: number;
  reason: string;
}

export interface TestCoverageSummary {
  total_source_files: number;
  tested_files: number;
  untested_files: number;
  test_files: number;
  coverage_percent: number;
  untested_core: TestCoverageFile[];
  notes: string[];
}

export interface KnowledgeSilo {
  path: string;
  primary_author: string;
  ownership: number;
  commits: number;
  bus_factor: number;
  reason: string;
}

export interface TechDebtFile {
  path: string;
  count: number;
}

export interface EnvVar {
  name: string;
  required: boolean;
  count: number;
}

export interface EntryPoint {
  path: string;
  kind: string;
  command: string;
  reason: string;
}

export interface ComplexFile {
  path: string;
  complexity: number;
  functions: number;
  reason: string;
}

export interface DocCoverageFile {
  path: string;
  code_lines: number;
  comment_lines: number;
  ratio: number;
  reason: string;
}

export interface DocCoverage {
  total_source_files: number;
  documented_files: number;
  undocumented_files: number;
  doc_percent: number;
  under_documented: DocCoverageFile[];
  notes: string[];
}

export interface SilentFailure {
  path: string;
  line: number;
  category: string;
  snippet: string;
  reason: string;
}

export interface ErrorHandling {
  total: number;
  files_affected: number;
  findings: SilentFailure[];
  notes: string[];
}

export interface ExternalService {
  name: string;
  category: string;
  note: string;
  file_count: number;
  example: string;
}

export interface Integrations {
  total: number;
  services: ExternalService[];
  categories: Record<string, number>;
  notes: string[];
}

export interface ActionItem {
  priority: string; // "high" | "medium" | "low"
  category: string;
  title: string;
  target: string;
  detail: string;
  effort: string; // "small" | "medium" | "large"
}

export interface ActionPlan {
  total: number;
  items: ActionItem[];
  notes: string[];
}

export interface Dependency {
  name: string;
  version: string;
  kind: string; // "runtime" | "dev" | "optional"
  manifest: string;
  purpose?: string | null;
}

export interface ApiRoute {
  method: string;
  path: string;
  handler?: string;
  description?: string;
  file: string;
  line: number;
}

export interface ApiMap {
  total: number;
  routes: ApiRoute[];
  frameworks: string[];
  notes: string[];
}

export interface HealthScore {
  score: number;
  grade: string; // A | B | C | D | F
  category_scores: Record<string, number>;
  weights: Record<string, number>;
  strengths: string[];
  weaknesses: string[];
  notes: string[];
}

export interface ActivityContributor {
  author: string;
  commits: number;
}

export interface ActivitySummary {
  available: boolean;
  total_commits: number;
  first_commit_days_ago?: number | null;
  last_commit_days_ago?: number | null;
  label: string; // active | slowing | quiet | stale | abandoned | unknown
  label_zh: string;
  top_contributors: ActivityContributor[];
  notes: string[];
}

export interface ProjectMeta {
  id: string;
  name: string;
  total_files: number;
  files: FileInfo[];
  reading_map?: {
    order: number;
    path: string;
    reason: string;
    kind?: string | null;
  }[];
  hotspots?: Hotspot[];
  architecture_layers?: ArchitectureLayer[];
  package_dependencies?: PackageDependency[];
  coupling_hotspots?: CouplingHotspot[];
  blast_radius?: BlastRadiusHotspot[];
  import_cycles?: ImportCycle[];
  orphan_modules?: OrphanModule[];
  health?: ProjectHealth;
  churn_hotspots?: ChurnHotspot[];
  co_change_couplings?: CoChangeCoupling[];
  risk_hotspots?: RiskHotspot[];
  test_coverage?: TestCoverageSummary;
  knowledge_silos?: KnowledgeSilo[];
  tech_debt_files?: TechDebtFile[];
  env_vars?: EnvVar[];
  entry_points?: EntryPoint[];
  complexity_files?: ComplexFile[];
  doc_coverage?: DocCoverage;
  error_handling?: ErrorHandling;
  integrations?: Integrations;
  action_plan?: ActionPlan;
  dependencies?: Dependency[];
  api_map?: ApiMap;
  activity?: ActivitySummary;
  health_score?: HealthScore;
}

export interface Annotation {
  line_start: number;
  line_end: number;
  annotation: string;
}

export interface GlossaryTerm {
  term: string;
  definition: string;
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
  const res = await apiFetch(`${BASE}/project/${projectId}`, {
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
  const res = await apiFetch(`${BASE}/project/upload`, {
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
  const res = await apiFetch(`${BASE}/project/github`, {
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

  const res = await apiFetch(`${BASE}/project/${projectId}/overview`, { headers });
  if (!res.ok || !res.body) {
    if (res.status === 429) {
      const err = await res.json().catch(() => ({ detail: tStatic("请求过于频繁", "Too many requests") }));
      onError(err.detail || tStatic("今日免费额度已用完，请配置 API Key", "Free tier exhausted for today — please configure an API key"));
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
        if (parsed.error) {
          onError(parsed.error);
          return;
        }
        if (parsed.chunk) onChunk(parsed.chunk);
        if (parsed.result) onResult(parsed.result);
        if (parsed.raw) onChunk(parsed.raw);
      } catch {
        // ignore parse errors in stream
      }
    }
  }
}

/** What a file conventionally is, inferred from its name alone. */
export interface FilePurpose {
  name: string;
  kind: string;
  explanation: string;
}

/** Get file content. */
export async function getFileContent(
  projectId: string,
  filePath: string
): Promise<{
  path: string;
  language: string;
  content: string;
  purpose: FilePurpose | null;
}> {
  const res = await apiFetch(
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
  const res = await apiFetch(
    `${BASE}/project/${projectId}/file/${encodeURIComponent(filePath)}/annotations`,
    { headers: getHeaders() }
  );
  if (!res.ok) {
    if (res.status === 429) {
      const err = await res.json().catch(() => ({ detail: tStatic("请求过于频繁", "Too many requests") }));
      throw new Error(err.detail || tStatic("今日免费额度已用完，请配置 API Key", "Free tier exhausted for today — please configure an API key"));
    }
    throw new Error("Failed to get annotations");
  }
  return res.json();
}

/** Ask a free-form question about a selected piece of code. */
export async function askQuestion(
  projectId: string,
  params: { question: string; code?: string; filePath?: string; language?: string }
): Promise<{ answer: string }> {
  const res = await apiFetch(`${BASE}/project/${projectId}/qa`, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({
      question: params.question,
      code: params.code ?? "",
      file_path: params.filePath ?? "",
      language: params.language ?? "",
    }),
  });
  if (!res.ok) {
    if (res.status === 429) {
      const err = await res.json().catch(() => ({ detail: tStatic("请求过于频繁", "Too many requests") }));
      throw new Error(err.detail || tStatic("今日免费额度已用完，请配置 API Key", "Free tier exhausted for today — please configure an API key"));
    }
    const err = await res.json().catch(() => ({ detail: "" }));
    throw new Error(err.detail || tStatic("没能获取回答，请重试。", "Couldn't get an answer — please try again."));
  }
  return res.json();
}

/** Apply a natural-language instruction to a code snippet (suggested edit). */
export async function editCode(
  projectId: string,
  params: { instruction: string; code: string; filePath?: string; language?: string }
): Promise<{ edited_code: string }> {
  const res = await apiFetch(`${BASE}/project/${projectId}/edit`, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({
      instruction: params.instruction,
      code: params.code,
      file_path: params.filePath ?? "",
      language: params.language ?? "",
    }),
  });
  if (!res.ok) {
    if (res.status === 429) {
      const err = await res.json().catch(() => ({ detail: tStatic("请求过于频繁", "Too many requests") }));
      throw new Error(err.detail || tStatic("今日免费额度已用完，请配置 API Key", "Free tier exhausted for today — please configure an API key"));
    }
    const err = await res.json().catch(() => ({ detail: "" }));
    throw new Error(err.detail || tStatic("没能改写，请重试。", "Couldn't rewrite — please try again."));
  }
  return res.json();
}

/** Get the jargon terms found in a file (deterministic, no API key needed). */
export async function getGlossary(
  projectId: string,
  filePath: string
): Promise<{ path: string; terms: GlossaryTerm[] }> {
  const res = await apiFetch(
    `${BASE}/project/${projectId}/file/${encodeURIComponent(filePath)}/glossary`,
    { headers: getHeaders() }
  );
  if (!res.ok) throw new Error("Failed to get glossary");
  return res.json();
}
