// Turn a raw backend / network error into a calm, actionable sentence a
// non-programmer can act on. Known cases get friendly guidance (and point at
// the gear menu where it helps); anything unrecognised falls back to the
// original message so power users still see specifics.

type Translate = (zh: string, en: string) => string;

export function friendlyError(raw: string, t: Translate): string {
  const msg = raw || "";
  const low = msg.toLowerCase();

  if (low.includes("429") || msg.includes("额度") || low.includes("rate limit")) {
    return t(
      "今天的免费额度用完了。点右上角的齿轮 ⚙ 填入自己的 API Key，就能继续无限使用。",
      "Today's free quota is used up. Click the gear icon (top-right) and add your own API key to keep going.",
    );
  }
  if (
    low.includes("401") ||
    low.includes("authentication") ||
    low.includes("unauthor") ||
    (low.includes("api") && low.includes("key")) ||
    low.includes("no auth credentials")
  ) {
    return t(
      "API Key 好像不对。点右上角的齿轮 ⚙ 重新填一下（OpenRouter 以 sk-or- 开头的 Key 最省事）。",
      "That API key didn't work. Re-enter it via the gear icon (top-right) — an OpenRouter key starting with sk-or- is the easiest.",
    );
  }
  if (low.includes("no readable source") || low.includes("no source")) {
    return t(
      "没在这个项目里找到能读的源代码。换一个包含代码文件的项目或仓库试试？",
      "No readable source code was found here. Try a project or repo that has code files in it.",
    );
  }
  if (low.includes("git") && low.includes("instal")) {
    return t(
      "从链接克隆需要用到 Git，但你电脑上好像没装。可以去 https://git-scm.com 装一个，或者直接把项目文件夹拖进来上传。",
      "Cloning from a URL needs Git, which doesn't seem to be installed. Get it at https://git-scm.com, or just upload the project folder instead.",
    );
  }
  if (low.includes("404") || low.includes("not found")) {
    return t(
      "找不到这个仓库。检查一下链接对不对、仓库是不是公开的。",
      "That repository couldn't be found. Check the URL, and that the repo is public.",
    );
  }
  if (low.includes("too large") || low.includes("size limit")) {
    return t(
      "这个仓库太大了，换一个小一点的试试。",
      "That repository is too large — try a smaller one.",
    );
  }
  if (
    low.includes("network") ||
    low.includes("failed to fetch") ||
    low.includes("timeout") ||
    low.includes("econn")
  ) {
    return t(
      "连不上服务器。检查一下网络，稍后再试。",
      "Couldn't reach the server. Check your connection and try again.",
    );
  }
  return msg;
}
