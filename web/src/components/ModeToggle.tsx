import { Moon, Sun, Monitor } from "lucide-react";
import { useTheme } from "./ThemeProvider";

export function ModeToggle() {
  const { theme, setTheme } = useTheme();

  return (
    <div className="flex items-center gap-1 bg-slate-100 dark:bg-slate-800 p-1 rounded-lg border border-slate-200 dark:border-slate-700">
      <button
        onClick={() => setTheme("light")}
        className={`p-1.5 rounded-md transition-colors ${
          theme === "light"
            ? "bg-white dark:bg-slate-700 shadow-sm text-slate-900 dark:text-slate-100"
            : "text-slate-500 hover:text-slate-900 dark:hover:text-slate-300"
        }`}
        title="Light Mode"
      >
        <Sun size={14} />
      </button>
      <button
        onClick={() => setTheme("dark")}
        className={`p-1.5 rounded-md transition-colors ${
          theme === "dark"
            ? "bg-white dark:bg-slate-700 shadow-sm text-slate-900 dark:text-slate-100"
            : "text-slate-500 hover:text-slate-900 dark:hover:text-slate-300"
        }`}
        title="Dark Mode"
      >
        <Moon size={14} />
      </button>
      <button
        onClick={() => setTheme("system")}
        className={`p-1.5 rounded-md transition-colors ${
          theme === "system"
            ? "bg-white dark:bg-slate-700 shadow-sm text-slate-900 dark:text-slate-100"
            : "text-slate-500 hover:text-slate-900 dark:hover:text-slate-300"
        }`}
        title="System"
      >
        <Monitor size={14} />
      </button>
    </div>
  );
}
