import { useCallback, useRef, useState } from "react";
import { useI18n } from "../lib/i18n";

interface Props {
  onFilesSelected: (files: { path: string; content: string }[], name: string) => void;
  disabled?: boolean;
}

// Folders that are dependencies, build output, or tooling state — never the
// source someone wants to read. Dropping a real project folder almost always
// drags these along, so skip them before reading megabytes off disk.
const SKIP_DIRS = new Set([
  ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
  ".idea", ".vscode", ".next", "dist", "build", ".tox",
  ".mypy_cache", ".pytest_cache", ".ruff_cache",
]);

function inSkippedDir(path: string): boolean {
  const dirs = path.split("/").slice(0, -1); // directory segments, excluding the filename
  return dirs.some((d) => SKIP_DIRS.has(d) || d.endsWith(".egg-info"));
}

export default function UploadZone({ onFilesSelected, disabled }: Props) {
  const { t } = useI18n();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);

  const processFiles = useCallback(
    async (fileList: FileList) => {
      const results: { path: string; content: string }[] = [];
      let projectName = "untitled";

      for (const file of Array.from(fileList)) {
        // webkitRelativePath gives us "folder/subfolder/file.py"
        const path = file.webkitRelativePath || file.name;

        // extract project name from the top-level folder
        if (file.webkitRelativePath) {
          const topDir = file.webkitRelativePath.split("/")[0];
          if (topDir) projectName = topDir;
        }

        // skip dependency / build / tooling folders, huge files, and dotfiles
        if (inSkippedDir(path)) continue;
        if (file.size > 100 * 1024) continue;
        if (file.name.startsWith(".")) continue;

        try {
          const content = await file.text();
          // basic binary check
          if (content.includes("\0")) continue;
          results.push({ path, content });
        } catch {
          // skip unreadable files
        }
      }

      if (results.length > 0) {
        onFilesSelected(results, projectName);
      }
    },
    [onFilesSelected]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      if (e.dataTransfer.files.length > 0) {
        processFiles(e.dataTransfer.files);
      }
    },
    [processFiles]
  );

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
      onClick={() => inputRef.current?.click()}
      className={`
        border-2 border-dashed rounded-2xl p-12 text-center cursor-pointer
        transition-all duration-200
        ${dragOver ? "border-blue-500 bg-blue-50" : "border-gray-300 hover:border-gray-400 hover:bg-gray-50"}
        ${disabled ? "opacity-50 pointer-events-none" : ""}
      `}
    >
      <input
        ref={inputRef}
        type="file"
        /* @ts-expect-error webkitdirectory is not in the type defs */
        webkitdirectory=""
        directory=""
        multiple
        className="hidden"
        onChange={(e) => {
          if (e.target.files) processFiles(e.target.files);
        }}
      />
      <div className="text-4xl mb-4">📂</div>
      <p className="text-lg font-medium text-gray-700">
        {t("拖入项目文件夹，或点击选择", "Drop a project folder, or click to choose")}
      </p>
      <p className="text-sm text-gray-500 mt-2">
        {t("支持任何包含源代码的文件夹", "Any folder with source code works")}
      </p>
    </div>
  );
}
