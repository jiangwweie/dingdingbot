import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

export type ConsoleTheme = 'dark' | 'light';

export const CONSOLE_THEME_STORAGE_KEY = 'brc-console-theme';

type ThemeState = {
  theme: ConsoleTheme;
  isDark: boolean;
  setTheme: (theme: ConsoleTheme) => void;
  toggleTheme: () => void;
};

const ThemeContext = createContext<ThemeState | null>(null);

function normalizeTheme(value: string | null | undefined): ConsoleTheme | null {
  if (value === 'dark' || value === 'light') return value;
  return null;
}

export function readStoredTheme(): ConsoleTheme {
  if (typeof window === 'undefined') return 'dark';
  return normalizeTheme(window.localStorage.getItem(CONSOLE_THEME_STORAGE_KEY)) || 'dark';
}

export function applyConsoleTheme(theme: ConsoleTheme) {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;
  root.classList.toggle('dark', theme === 'dark');
  root.dataset.theme = theme;
  root.style.colorScheme = theme;
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<ConsoleTheme>(() => readStoredTheme());

  useEffect(() => {
    applyConsoleTheme(theme);
    window.localStorage.setItem(CONSOLE_THEME_STORAGE_KEY, theme);
  }, [theme]);

  const setTheme = useCallback((nextTheme: ConsoleTheme) => {
    setThemeState(nextTheme);
  }, []);

  const toggleTheme = useCallback(() => {
    setThemeState((current) => (current === 'dark' ? 'light' : 'dark'));
  }, []);

  const value = useMemo(
    () => ({
      theme,
      isDark: theme === 'dark',
      setTheme,
      toggleTheme,
    }),
    [theme, setTheme, toggleTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeState {
  const value = useContext(ThemeContext);
  if (!value) throw new Error('useTheme must be used inside ThemeProvider');
  return value;
}
