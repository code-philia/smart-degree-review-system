export type StatusTone = 'success' | 'warning' | 'danger' | 'info' | 'neutral';

const TONE_CLASSES: Record<StatusTone, string> = {
  success: 'bg-success-100 text-success-600',
  warning: 'bg-warning-100 text-warning-600',
  danger: 'bg-danger-100 text-danger-600',
  info: 'bg-brand-100 text-brand-600',
  neutral: 'bg-slate-100 text-slate-600',
};

type StatusBadgeProps = {
  tone?: StatusTone;
  children: React.ReactNode;
};

function StatusBadge({ tone = 'neutral', children }: StatusBadgeProps) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-bold ${TONE_CLASSES[tone]}`}>
      {children}
    </span>
  );
}

export default StatusBadge;
