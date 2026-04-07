import { useState } from "react";
import { useNavigate } from "react-router-dom";
import UploadZone from "../components/UploadZone";
import ApiKeyModal from "../components/ApiKeyModal";
import { uploadProject, cloneGitHub } from "../lib/api";
import { useProjectStore } from "../stores/project";

export default function Home() {
  const navigate = useNavigate();
  const { setProject, setLoading, setError, loading, error, reset } =
    useProjectStore();

  const [githubUrl, setGithubUrl] = useState("");
  const [showKeyModal, setShowKeyModal] = useState(false);

  const handleUpload = async (
    files: { path: string; content: string }[],
    name: string
  ) => {
    reset();
    setLoading(true);
    try {
      const proj = await uploadProject(files, name);
      setProject(proj);
      navigate(`/project/${proj.id}`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "上传失败");
    } finally {
      setLoading(false);
    }
  };

  const handleGitHub = async () => {
    if (!githubUrl.trim()) return;
    reset();
    setLoading(true);
    try {
      const proj = await cloneGitHub(githubUrl.trim());
      setProject(proj);
      navigate(`/project/${proj.id}`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "克隆失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-4">
      {/* Settings button (top-right) */}
      <button
        onClick={() => setShowKeyModal(true)}
        className="fixed top-4 right-4 p-2 text-gray-400 hover:text-gray-600
                   hover:bg-gray-100 rounded-lg transition-colors"
        title="API Key 设置"
      >
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
        </svg>
      </button>
      <ApiKeyModal open={showKeyModal} onClose={() => setShowKeyModal(false)} />

      <div className="max-w-2xl w-full">
        {/* Header */}
        <div className="text-center mb-10">
          <h1 className="text-4xl font-bold text-gray-900 mb-2">
            码上懂 <span className="text-blue-600">CodeABC</span>
          </h1>
          <p className="text-lg text-gray-600">
            不用学编程，也能读懂代码
          </p>
        </div>

        {/* Upload zone */}
        <UploadZone onFilesSelected={handleUpload} disabled={loading} />

        {/* Divider */}
        <div className="flex items-center my-6">
          <div className="flex-1 border-t border-gray-200" />
          <span className="px-4 text-sm text-gray-400">或者</span>
          <div className="flex-1 border-t border-gray-200" />
        </div>

        {/* GitHub URL input */}
        <div className="flex gap-3">
          <input
            type="text"
            value={githubUrl}
            onChange={(e) => setGithubUrl(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleGitHub()}
            placeholder="粘贴 GitHub 仓库链接，如 https://github.com/user/repo"
            className="flex-1 px-4 py-3 border border-gray-300 rounded-xl text-base
                       focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            disabled={loading}
          />
          <button
            onClick={handleGitHub}
            disabled={loading || !githubUrl.trim()}
            className="px-6 py-3 bg-blue-600 text-white rounded-xl font-medium
                       hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed
                       transition-colors"
          >
            {loading ? "加载中..." : "分析"}
          </button>
        </div>

        {/* Error message */}
        {error && (
          <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
            {error}
          </div>
        )}

        {/* Loading indicator */}
        {loading && (
          <div className="mt-6 text-center">
            <div className="inline-block w-8 h-8 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
            <p className="mt-2 text-sm text-gray-500">正在分析项目...</p>
          </div>
        )}
      </div>
    </div>
  );
}
