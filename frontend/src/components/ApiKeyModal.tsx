import { useState, useEffect } from "react";

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function ApiKeyModal({ open, onClose }: Props) {
  const [key, setKey] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (open) {
      setKey(localStorage.getItem("codeabc_api_key") || "");
      setSaved(false);
    }
  }, [open]);

  const handleSave = () => {
    if (key.trim()) {
      localStorage.setItem("codeabc_api_key", key.trim());
    } else {
      localStorage.removeItem("codeabc_api_key");
    }
    setSaved(true);
    setTimeout(() => onClose(), 800);
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-2xl shadow-xl w-full max-w-md mx-4 p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold text-gray-900 mb-1">API Key 设置</h2>
        <p className="text-sm text-gray-500 mb-4">
          填入你自己的 API Key 可以无限使用。留空则使用免费额度（每天 20 次）。
        </p>

        <input
          type="password"
          value={key}
          onChange={(e) => setKey(e.target.value)}
          placeholder="sk-... 或其他 LLM 提供商的 Key"
          className="w-full px-4 py-3 border border-gray-300 rounded-xl text-sm
                     focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />

        <p className="text-xs text-gray-400 mt-2 mb-4">
          Key 仅存在浏览器本地，不会上传到任何服务器。
          支持 OpenAI / Claude / DeepSeek / Kimi 等所有 litellm 兼容的 Key。
        </p>

        <div className="flex gap-3 justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800"
          >
            取消
          </button>
          <button
            onClick={handleSave}
            className="px-5 py-2 bg-blue-600 text-white text-sm rounded-lg
                       hover:bg-blue-700 transition-colors"
          >
            {saved ? "已保存 ✓" : "保存"}
          </button>
        </div>
      </div>
    </div>
  );
}
