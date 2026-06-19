/* eslint-disable react-refresh/only-export-components -- context provider,
   hook, and toggle are intentionally colocated for this small app */
import {
  createContext,
  useCallback,
  useContext,
  useState,
  type ReactNode,
} from "react";

// Lightweight i18n for a small app: instead of maintaining string keys, call
// `t(zh, en)` inline with both variants. The active language picks one. This
// keeps the diff close to the original markup and avoids a separate key file.

export type Lang = "zh" | "en";

const STORAGE_KEY = "codeabc-lang";

interface I18nValue {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (zh: string, en: string) => string;
}

const I18nContext = createContext<I18nValue | null>(null);

function detectInitial(): Lang {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "zh" || saved === "en") return saved;
    return navigator.language?.toLowerCase().startsWith("zh") ? "zh" : "en";
  } catch {
    return "zh";
  }
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(detectInitial);

  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    try {
      localStorage.setItem(STORAGE_KEY, l);
    } catch {
      // localStorage unavailable (private mode etc.) — keep in-memory only
    }
  }, []);

  const t = useCallback(
    (zh: string, en: string) => (lang === "zh" ? zh : en),
    [lang],
  );

  return (
    <I18nContext.Provider value={{ lang, setLang, t }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n(): I18nValue {
  const ctx = useContext(I18nContext);
  if (!ctx) {
    throw new Error("useI18n must be used within an I18nProvider");
  }
  return ctx;
}

/** Header button that flips between Chinese and English. */
export function LanguageToggle({ className = "" }: { className?: string }) {
  const { lang, setLang } = useI18n();
  return (
    <button
      onClick={() => setLang(lang === "zh" ? "en" : "zh")}
      className={
        "p-2 text-sm font-medium text-gray-500 hover:text-gray-800 " +
        "hover:bg-gray-100 rounded-lg transition-colors " +
        className
      }
      title={lang === "zh" ? "Switch to English" : "切换到中文"}
      aria-label="Toggle language"
    >
      {lang === "zh" ? "EN" : "中"}
    </button>
  );
}
