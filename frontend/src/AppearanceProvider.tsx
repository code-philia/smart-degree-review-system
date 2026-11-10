import type { PropsWithChildren } from 'react';
import { ThemeProvider } from 'next-themes';
import { useMatch } from 'react-router-dom';

export function AppearanceProvider({ children }: PropsWithChildren) {
  const isSignIn = Boolean(useMatch('/auth/*'));
  return (
    <ThemeProvider
      attribute="class"
      storageKey="sjtu-ui-theme"
      defaultTheme="light"
      enableSystem
      disableTransitionOnChange
      forcedTheme={isSignIn ? 'light' : undefined}
    >
      {children}
    </ThemeProvider>
  );
}
