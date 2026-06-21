/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Backend API base URL. Defaults to "/api" on the web; the desktop build
   *  sets it to the full backend origin since it can't rely on a same-origin proxy. */
  readonly VITE_API_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
