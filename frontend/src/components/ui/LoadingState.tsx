type LoadingStateProps = {
  label?: string;
  compact?: boolean;
};

function LoadingState({ label = '正在加载…', compact = false }: LoadingStateProps) {
  return (
    <div
      className={`flex items-center justify-center gap-3 text-sm font-semibold text-slate-500 ${compact ? 'py-6' : 'py-16'}`}
      role="status"
      aria-live="polite"
    >
      <span
        className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-brand-500"
        aria-hidden="true"
      />
      {label}
    </div>
  );
}

export default LoadingState;
