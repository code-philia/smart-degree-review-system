import { Moon, Sun } from 'lucide-react';
import { useTheme } from 'next-themes';

export function SupervisionThemeButton() {
  const { resolvedTheme, setTheme } = useTheme();
  const dark = resolvedTheme === 'dark';
  return <button type="button" className="sup-theme-toggle" aria-label={dark ? '切换到浅色模式' : '切换到深色模式'} onClick={() => setTheme(dark ? 'light' : 'dark')}>
    {dark ? <Sun size={17} /> : <Moon size={17} />}<span>{dark ? '浅色模式' : '深色模式'}</span>
  </button>;
}
