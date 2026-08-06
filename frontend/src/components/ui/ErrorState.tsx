import type { ReactNode } from 'react';
import { Button } from './Button';

type ErrorStateProps = {
  title?: string;
  message: ReactNode;
  onRetry?: () => void;
  retryLabel?: string;
};

function ErrorState({ title = '加载失败', message, onRetry, retryLabel = '重试' }: ErrorStateProps) {
  return (
    <div
      className="flex flex-col items-center gap-3 rounded-xl border border-danger-100 bg-danger-100/40 px-6 py-10 text-center"
      role="alert"
    >
      <p className="text-sm font-bold text-danger-600">{title}</p>
      <p className="max-w-md text-sm leading-6 text-slate-600">{message}</p>
      {onRetry ? (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          {retryLabel}
        </Button>
      ) : null}
    </div>
  );
}

export default ErrorState;
