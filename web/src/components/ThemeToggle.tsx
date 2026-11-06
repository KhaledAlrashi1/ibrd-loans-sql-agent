"use client";

// Follows the OS by default; a choice is stored per browser. The inline script in layout.tsx applies a
// stored choice before the first paint, so there is no flash.

import { useEffect, useState } from "react";
import { IconMonitor, IconMoon, IconSun } from "./icons";

type Theme = "system" | "light" | "dark";
const OPTIONS: { value: Theme; label: string; Icon: (p: { size?: number }) => React.ReactElement }[] = [
  { value: "system", label: "Match system theme", Icon: IconMonitor },
  { value: "light", label: "Light theme", Icon: IconSun },
  { value: "dark", label: "Dark theme", Icon: IconMoon },
];

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("system");

  useEffect(() => {
    const t = document.documentElement.dataset.theme;
    if (t === "light" || t === "dark") setTheme(t);
  }, []);

  function choose(t: Theme) {
    setTheme(t);
    const root = document.documentElement;
    try {
      if (t === "system") localStorage.removeItem("theme");
      else localStorage.setItem("theme", t);
    } catch { /* storage blocked: the choice lasts for this page only */ }
    if (t === "system") delete root.dataset.theme;
    else root.dataset.theme = t;
  }

  return (
    <div className="theme" role="radiogroup" aria-label="Colour theme">
      {OPTIONS.map(({ value, label, Icon }) => (
        <button key={value} type="button" role="radio" aria-checked={theme === value} aria-label={label}
          title={label} onClick={() => choose(value)}>
          <Icon />
        </button>
      ))}
    </div>
  );
}
