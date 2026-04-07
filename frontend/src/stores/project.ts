import { create } from "zustand";
import type { ProjectMeta, ProjectOverview, Annotation } from "../lib/api";

interface ProjectState {
  // current project
  project: ProjectMeta | null;
  overview: ProjectOverview | null;
  overviewRaw: string; // streaming raw text
  loading: boolean;
  error: string | null;

  // annotations cache: filePath -> annotations
  annotationsCache: Record<string, Annotation[]>;

  setProject: (p: ProjectMeta) => void;
  setOverview: (o: ProjectOverview) => void;
  appendOverviewRaw: (chunk: string) => void;
  resetOverviewRaw: () => void;
  setLoading: (v: boolean) => void;
  setError: (e: string | null) => void;
  cacheAnnotations: (path: string, anns: Annotation[]) => void;
  reset: () => void;
}

export const useProjectStore = create<ProjectState>((set) => ({
  project: null,
  overview: null,
  overviewRaw: "",
  loading: false,
  error: null,
  annotationsCache: {},

  setProject: (p) => set({ project: p }),
  setOverview: (o) => set({ overview: o }),
  appendOverviewRaw: (chunk) =>
    set((s) => ({ overviewRaw: s.overviewRaw + chunk })),
  resetOverviewRaw: () => set({ overviewRaw: "" }),
  setLoading: (v) => set({ loading: v }),
  setError: (e) => set({ error: e }),
  cacheAnnotations: (path, anns) =>
    set((s) => ({
      annotationsCache: { ...s.annotationsCache, [path]: anns },
    })),
  reset: () =>
    set({
      project: null,
      overview: null,
      overviewRaw: "",
      loading: false,
      error: null,
      annotationsCache: {},
    }),
}));
