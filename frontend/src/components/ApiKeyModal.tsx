import { useEffect, useState } from "react";
import { useI18n } from "../lib/i18n";
import {
  listProtocols,
  checkProtocol,
  discoverModels,
  bareModelId,
  type Protocol,
  type CheckResult,
  type DiscoveredModel,
} from "../lib/protocols";

interface Props {
  open: boolean;
  onClose: () => void;
}

type DiscState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; count: number }
  | { kind: "none"; msg: string }
  | { kind: "error"; msg: string };

function saveLocal(key: string, value: string): void {
  try {
    if (value) localStorage.setItem(key, value);
    else localStorage.removeItem(key);
  } catch {
    // localStorage unavailable (private mode etc.); keep in-memory only
  }
}

export default function ApiKeyModal({ open, onClose }: Props) {
  if (!open) return null;
  return <ProviderForm onClose={onClose} />;
}

function ProviderForm({ onClose }: { onClose: () => void }) {
  const { t } = useI18n();
  const [setupMode, setSetupMode] = useState<"simple" | "advanced">(() =>
    localStorage.getItem("codeabc_protocol") ||
    localStorage.getItem("codeabc_api_base") ||
    localStorage.getItem("codeabc_model")
      ? "advanced"
      : "simple",
  );
  const [protocols, setProtocols] = useState<Protocol[]>([]);
  const [protocolId, setProtocolId] = useState(
    () => localStorage.getItem("codeabc_protocol") || "",
  );
  const [baseUrl, setBaseUrl] = useState(
    () => localStorage.getItem("codeabc_api_base") || "",
  );
  const [apiKey, setApiKey] = useState(
    () => localStorage.getItem("codeabc_api_key") || "",
  );
  const [showKey, setShowKey] = useState(false);
  const [model, setModel] = useState(
    () => localStorage.getItem("codeabc_model") || "",
  );
  const [manualModel, setManualModel] = useState(() =>
    bareModelId(localStorage.getItem("codeabc_model") || ""),
  );
  const [manualMode, setManualMode] = useState(false);
  const [disc, setDisc] = useState<DiscState>({ kind: "idle" });
  const [models, setModels] = useState<DiscoveredModel[]>([]);
  const [checking, setChecking] = useState(false);
  const [check, setCheck] = useState<CheckResult | null>(null);

  useEffect(() => {
    listProtocols()
      .then((ps) => {
        setProtocols(ps);
        setProtocolId((cur) => cur || ps[0]?.id || "");
      })
      .catch(() => setProtocols([]));
  }, []);

  const selected = protocols.find((p) => p.id === protocolId) ?? null;

  function qualify(p: Protocol | null, id: string): string {
    if (!p || !id) return id;
    const prefix = p.litellm_prefix || "";
    if (!prefix || id.startsWith(prefix)) return id;
    return `${prefix}${id}`;
  }

  const bareModel = manualMode ? manualModel.trim() : bareModelId(model);

  async function runDiscover() {
    if (!baseUrl.trim() || !protocolId) {
      setDisc({
        kind: "error",
        msg: t(
          "先填写 Base URL 并选择 API 格式。",
          "Fill in the Base URL and pick an API format first.",
        ),
      });
      return;
    }
    setDisc({ kind: "loading" });
    setModels([]);
    try {
      const r = await discoverModels(
        protocolId,
        baseUrl.trim(),
        apiKey.trim() || undefined,
      );
      if (r.discoverable && (r.models?.length ?? 0) > 0) {
        setModels(r.models ?? []);
        setDisc({ kind: "ok", count: r.count });
        setManualMode(false);
      } else if (r.discoverable) {
        setManualMode(true);
        setDisc({
          kind: "none",
          msg: t(
            "端点可达但未返回模型，请手动填写模型 ID。",
            "Endpoint reachable but returned no models; enter a model ID.",
          ),
        });
      } else if (r.status_code === 401 || r.status_code === 403) {
        setDisc({
          kind: "error",
          msg: t(
            "API Key 被该端点拒绝（401/403），请检查 Key 后重新获取。",
            "The endpoint rejected the API key (401/403); check the key and fetch again.",
          ),
        });
      } else {
        setManualMode(true);
        setDisc({
          kind: "none",
          msg:
            r.error ||
            t(
              "该端点不提供模型列表接口，请手动填写模型 ID。",
              "This endpoint exposes no models list; enter a model ID.",
            ),
        });
      }
    } catch {
      setDisc({
        kind: "error",
        msg: t("连不上 CodeABC 后端。", "Could not reach the CodeABC server."),
      });
    }
    setCheck(null);
  }

  async function runCheck() {
    setChecking(true);
    setCheck(null);
    try {
      const res = await checkProtocol({
        protocol: protocolId || undefined,
        api_base: baseUrl.trim() || undefined,
        api_key: apiKey.trim() || undefined,
        model: bareModel || undefined,
      });
      setCheck(res);
    } catch {
      setCheck({
        ok: false,
        base_url: baseUrl,
        status_code: null,
        masked_key: "",
        diagnosis: "Could not reach the CodeABC server.",
        diagnosis_zh: "连不上 CodeABC 后端。",
      });
    } finally {
      setChecking(false);
    }
  }

  function onProtocolChange(id: string) {
    const nextProtocol = protocols.find((p) => p.id === id) ?? null;
    const nextBareModel = manualMode ? manualModel.trim() : bareModelId(model);
    setProtocolId(id);
    setModel(qualify(nextProtocol, nextBareModel));
    setManualModel(nextBareModel);
    setCheck(null);
    setDisc({ kind: "idle" });
    setModels([]);
  }

  function onBaseChange(value: string) {
    setBaseUrl(value);
    setCheck(null);
    setDisc({ kind: "idle" });
    setModels([]);
  }

  function onKeyChange(value: string) {
    setApiKey(value);
    setCheck(null);
  }

  function pickModel(nextModel: DiscoveredModel) {
    setModel(nextModel.litellm_model);
    setManualModel(nextModel.id);
    setCheck(null);
  }

  function onManual(value: string) {
    setManualModel(value);
    setModel(qualify(selected, value.trim()));
    setCheck(null);
  }

  function finishSimple() {
    saveLocal("codeabc_api_key", apiKey.trim());
    saveLocal("codeabc_api_base", "");
    saveLocal("codeabc_model", "");
    saveLocal("codeabc_protocol", "");
    onClose();
  }

  function finishAdvanced() {
    if (!check?.ok || !selected || !bareModel) return;
    saveLocal("codeabc_api_key", apiKey.trim());
    saveLocal("codeabc_api_base", check.base_url);
    saveLocal("codeabc_model", qualify(selected, bareModel));
    saveLocal("codeabc_protocol", protocolId);
    onClose();
  }

  const inputCls =
    "w-full px-4 py-3 border border-gray-300 rounded-xl text-sm " +
    "focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent";
  const labelCls = "block text-sm font-medium text-gray-700 mb-1.5";
  const stepCls =
    "text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2";

  const keyField = (
    <div>
      <label className={labelCls} htmlFor="codeabc-api-key">
        {t("API Key", "API Key")}
      </label>
      <div className="relative">
        <input
          id="codeabc-api-key"
          className={inputCls + " pr-11"}
          type={showKey ? "text" : "password"}
          value={apiKey}
          onChange={(e) => onKeyChange(e.target.value)}
          placeholder={t("输入 API Key", "Enter API Key")}
          autoComplete="off"
        />
        <button
          type="button"
          onClick={() => setShowKey((current) => !current)}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
          aria-label={t("显示/隐藏 Key", "Show/hide key")}
        >
          {showKey ? (
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l18 18" />
            </svg>
          ) : (
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
            </svg>
          )}
        </button>
      </div>
    </div>
  );

  const openRouterLink = (
    <a
      href="https://openrouter.ai/keys"
      target="_blank"
      rel="noopener noreferrer"
      className="inline-block text-xs text-blue-600 hover:text-blue-700"
    >
      {t(
        "还没有 Key？去 OpenRouter 注册一个（sk-or- 开头）→",
        "Need a key? Get one from OpenRouter (it starts with sk-or-) →",
      )}
    </a>
  );

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-2xl shadow-xl w-full max-w-lg max-h-[88vh] overflow-y-auto p-6 mx-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-lg font-semibold text-gray-900">
            {t("模型服务商设置", "Model provider settings")}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg"
            aria-label={t("关闭", "Close")}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="grid grid-cols-2 gap-2 mb-5 rounded-xl bg-gray-100 p-1">
          <button
            type="button"
            aria-pressed={setupMode === "simple"}
            onClick={() => setSetupMode("simple")}
            className={
              "py-2 rounded-lg text-sm font-medium " +
              (setupMode === "simple"
                ? "bg-white text-blue-700 shadow-sm"
                : "text-gray-500 hover:text-gray-700")
            }
          >
            {t("简单 Key", "Simple key")}
          </button>
          <button
            type="button"
            aria-pressed={setupMode === "advanced"}
            onClick={() => setSetupMode("advanced")}
            className={
              "py-2 rounded-lg text-sm font-medium " +
              (setupMode === "advanced"
                ? "bg-white text-blue-700 shadow-sm"
                : "text-gray-500 hover:text-gray-700")
            }
          >
            {t("自定义网关", "Custom gateway")}
          </button>
        </div>

        {setupMode === "simple" ? (
          <div>
            <p className="text-sm text-gray-500 mb-4">
              {t(
                "粘贴 OpenRouter、OpenAI、Anthropic 或其他兼容服务商的 Key 即可。OpenRouter 会自动选择性价比高的模型，不用填写网关或模型 ID。",
                "Paste an OpenRouter, OpenAI, Anthropic, or another compatible provider key. OpenRouter picks a cost-effective model automatically, with no gateway or model ID to configure.",
              )}
            </p>
            {keyField}
            <p className="text-xs text-gray-400 mt-2 mb-3">
              {t(
                "Key 只保存在浏览器本地。留空并保存即可回到每天 20 次的免费额度。",
                "The key is stored only in this browser. Save an empty key to return to the free tier (20 requests/day).",
              )}
            </p>
            {openRouterLink}
            <div className="flex gap-3 justify-end mt-6">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800"
              >
                {t("取消", "Cancel")}
              </button>
              <button
                type="button"
                onClick={finishSimple}
                className="px-5 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700"
              >
                {t("保存", "Save")}
              </button>
            </div>
          </div>
        ) : (
          <div>
            <div className={stepCls}>{t("1 · 连接信息", "1 · Endpoint")}</div>
            <div className="mb-4">
              <label className={labelCls} htmlFor="codeabc-api-base">
                Base URL
              </label>
              <input
                id="codeabc-api-base"
                className={inputCls}
                value={baseUrl}
                onChange={(e) => onBaseChange(e.target.value)}
                placeholder={selected?.base_hint || "https://api.example.com/v1"}
              />
              <p className="text-xs text-gray-400 mt-1">
                {t(
                  "OpenAI 系需以 /v1 结尾，Anthropic 系填根地址；系统会自动归一。",
                  "OpenAI-style ends with /v1, Anthropic-style uses the root; auto-normalised.",
                )}
              </p>
            </div>
            <div className="mb-4">
              <label className={labelCls} htmlFor="codeabc-api-protocol">
                {t("API 格式", "API format")}
              </label>
              <select
                id="codeabc-api-protocol"
                className={inputCls}
                value={protocolId}
                onChange={(e) => onProtocolChange(e.target.value)}
              >
                {protocols.length === 0 && (
                  <option value="">{t("加载中…", "Loading…")}</option>
                )}
                {protocols.map((p) => (
                  <option key={p.id} value={p.id}>
                    {t(p.label_zh, p.label)}
                  </option>
                ))}
              </select>
              {selected && (
                <p className="text-xs text-gray-400 mt-1">
                  {t(selected.wire_zh, selected.wire)}
                </p>
              )}
            </div>
            <div className="mb-3">{keyField}</div>
            <div className="mb-4">{openRouterLink}</div>
            <p className="text-xs text-gray-400 mb-5">
              {t(
                "验证成功并点击完成后才保存这组设置；取消不会改动正在使用的配置。无 Key 的本地网关可以留空。",
                "These settings are saved only after a successful check and clicking Done. Cancel leaves the active configuration unchanged. Local gateways that do not need a key can leave it empty.",
              )}
            </p>

            <div className={stepCls}>{t("2 · 模型", "2 · Model")}</div>
            <button
              type="button"
              onClick={runDiscover}
              disabled={disc.kind === "loading"}
              className="w-full py-2.5 mb-3 rounded-xl text-sm font-medium border border-blue-600 text-blue-700 hover:bg-blue-50 disabled:opacity-50 transition-colors"
            >
              {disc.kind === "loading"
                ? t("探测中…", "Probing…")
                : t("获取模型列表", "Fetch model list")}
            </button>

            {disc.kind === "ok" && (
              <div className="mb-3 rounded-xl px-4 py-2.5 text-sm bg-green-50 text-green-800">
                {t("可自动发现", "Auto-discovery available")} · {disc.count}{" "}
                {t("个模型", "models")}
              </div>
            )}
            {(disc.kind === "none" || disc.kind === "error") && (
              <div
                className={
                  "mb-3 rounded-xl px-4 py-2.5 text-sm " +
                  (disc.kind === "error"
                    ? "bg-red-50 text-red-700"
                    : "bg-amber-50 text-amber-800")
                }
              >
                {disc.msg}
              </div>
            )}
            {disc.kind === "idle" && (
              <p className="text-xs text-gray-400 -mt-1 mb-3">
                {t(
                  "先探测该端点能否自动列出模型；不能则需手动填写模型 ID。",
                  "Probe whether this endpoint can list its models; otherwise enter a model ID.",
                )}
              </p>
            )}

            {disc.kind === "ok" && !manualMode && (
              <div className="mb-3">
                <select
                  aria-label={t("选择模型", "Select model")}
                  className={inputCls}
                  value={model}
                  onChange={(e) => {
                    const nextModel = models.find(
                      (item) => item.litellm_model === e.target.value,
                    );
                    if (nextModel) pickModel(nextModel);
                  }}
                >
                  <option value="">{t("请选择模型…", "Select a model…")}</option>
                  {models.map((item) => (
                    <option
                      key={item.litellm_model}
                      value={item.litellm_model}
                      disabled={!item.chat}
                    >
                      {item.id}
                      {item.chat
                        ? ""
                        : ` · ${t(item.chat_reason_zh, item.chat_reason)}`}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={() => setManualMode(true)}
                  className="text-xs text-blue-600 hover:underline mt-1.5"
                >
                  {t("改为手动输入模型 ID", "Enter a model ID manually instead")}
                </button>
              </div>
            )}

            {(manualMode || disc.kind === "none") && (
              <div className="mb-3">
                <label className={labelCls} htmlFor="codeabc-model-id">
                  {disc.kind === "ok"
                    ? t("手动模型 ID", "Manual model ID")
                    : t("模型 ID（必填）", "Model ID (required)")}
                </label>
                <input
                  id="codeabc-model-id"
                  className={inputCls}
                  value={manualModel}
                  onChange={(e) => onManual(e.target.value)}
                  placeholder={t("如 qwen3.8-flash", "e.g. qwen3.8-flash")}
                />
                {disc.kind === "ok" && (
                  <button
                    type="button"
                    onClick={() => setManualMode(false)}
                    className="text-xs text-blue-600 hover:underline mt-1.5"
                  >
                    {t("从列表选择", "Pick from the discovered list")}
                  </button>
                )}
              </div>
            )}

            <div className={stepCls + " mt-5"}>{t("3 · 验证", "3 · Verify")}</div>
            <button
              type="button"
              onClick={runCheck}
              disabled={checking || !bareModel}
              className="w-full py-2.5 mb-4 rounded-xl text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {checking ? t("测试中…", "Testing…") : t("测试连接", "Test connection")}
            </button>
            {!bareModel && (
              <p className="text-xs text-gray-400 -mt-2 mb-4">
                {t("请先在第 2 步选择或填写模型。", "Choose or enter a model in step 2 first.")}
              </p>
            )}
            {check && (
              <div
                className={
                  "mb-4 rounded-xl px-4 py-3 text-sm " +
                  (check.ok ? "bg-green-50 text-green-800" : "bg-red-50 text-red-700")
                }
              >
                {check.ok ? (
                  <span>
                    {t("连接成功", "Connected")}
                    {check.masked_key && ` · ${check.masked_key}`}
                  </span>
                ) : (
                  <span>{t(check.diagnosis_zh || "", check.diagnosis || "")}</span>
                )}
              </div>
            )}
            <div className="flex gap-3 justify-end">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800"
              >
                {t("取消", "Cancel")}
              </button>
              <button
                type="button"
                onClick={finishAdvanced}
                disabled={!check?.ok}
                className="px-5 py-2 rounded-lg text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50"
              >
                {t("完成", "Done")}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
