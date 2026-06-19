import { useState } from "react";
import { useI18n } from "../lib/i18n";

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function ApiKeyModal({ open, onClose }: Props) {
  if (!open) return null;

  return <ApiKeyDialog onClose={onClose} />;
}

function ApiKeyDialog({ onClose }: { onClose: () => void }) {
  const { t } = useI18n();
  const [key, setKey] = useState(() => localStorage.getItem("codeabc_api_key") || "");
  const [saved, setSaved] = useState(false);

  const handleSave = () => {
    if (key.trim()) {
      localStorage.setItem("codeabc_api_key", key.trim());
    } else {
      localStorage.removeItem("codeabc_api_key");
    }
    setSaved(true);
    setTimeout(() => onClose(), 800);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-2xl shadow-xl w-full max-w-md mx-4 p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold text-gray-900 mb-1">
          {t("API Key 设置", "API Key settings")}
        </h2>
        <p className="text-sm text-gray-500 mb-4">
          {t(
            "填入你自己的 API Key 可以无限使用。留空则使用免费额度（每天 20 次）。",
            "Add your own API key for unlimited use. Leave it blank to use the free tier (20/day).",
          )}
        </p>

        <input
          type="password"
          value={key}
          onChange={(e) => setKey(e.target.value)}
          placeholder={t(
            "sk-... 或其他 LLM 提供商的 Key",
            "sk-... or a key from another LLM provider",
          )}
          className="w-full px-4 py-3 border border-gray-300 rounded-xl text-sm
                     focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />

        <p className="text-xs text-gray-400 mt-2 mb-4">
          {t(
            "Key 仅存在浏览器本地，不会上传到任何服务器。支持 OpenAI / Claude / DeepSeek / Kimi 等所有 litellm 兼容的 Key。",
            "The key stays in your browser and is never uploaded to any server. Works with OpenAI / Claude / DeepSeek / Kimi and any litellm-compatible key.",
          )}
        </p>

        <div className="flex gap-3 justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800"
          >
            {t("取消", "Cancel")}
          </button>
          <button
            onClick={handleSave}
            className="px-5 py-2 bg-blue-600 text-white text-sm rounded-lg
                       hover:bg-blue-700 transition-colors"
          >
            {saved ? t("已保存 ✓", "Saved ✓") : t("保存", "Save")}
          </button>
        </div>
      </div>
    </div>
  );
}
