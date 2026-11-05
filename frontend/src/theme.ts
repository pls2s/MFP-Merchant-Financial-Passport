import { useEffect, useState } from "react";

export type Theme = "dark" | "light";

const KEY = "mfp-theme";

/** Saved choice, else the OS preference, else light (light-first). Storage may be blocked — never throw. */
export function initialTheme(): Theme {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === "dark" || saved === "light") return saved;
  } catch { /* private window / blocked storage */ }
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme;
}

export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(() => (document.documentElement.dataset.theme as Theme) || initialTheme());
  useEffect(() => {
    applyTheme(theme);
    try { localStorage.setItem(KEY, theme); } catch { /* ignore */ }
    window.dispatchEvent(new CustomEvent("mfp-theme", { detail: theme }));
  }, [theme]);
  return [theme, () => setTheme((t) => (t === "dark" ? "light" : "dark"))];
}

/** Resolved CSS custom properties — WebGL materials cannot read var(--x). Re-reads on theme change. */
export function useTokens<K extends string>(names: readonly K[]): Record<K, string> {
  const read = () => {
    const style = getComputedStyle(document.documentElement);
    return Object.fromEntries(names.map((n) => [n, style.getPropertyValue(`--${n}`).trim() || "#888"])) as Record<K, string>;
  };
  const [tokens, setTokens] = useState(read);
  useEffect(() => {
    const onChange = () => requestAnimationFrame(() => setTokens(read()));
    window.addEventListener("mfp-theme", onChange);
    return () => window.removeEventListener("mfp-theme", onChange);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return tokens;
}

export const prefersReducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
