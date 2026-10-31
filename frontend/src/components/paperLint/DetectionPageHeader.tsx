export function DetectionPageHeader({ title, description }: { title: string; description?: string }) {
  return (
    <header className="px-1 pt-1">
      <p className="mb-1.5 text-sm font-medium text-brand-700">论文规范性检测</p>
      <h1 className="text-2xl font-bold tracking-tight text-slate-950 sm:text-3xl">{title}</h1>
      {description ? <p className="mt-2 text-sm leading-6 text-slate-600">{description}</p> : null}
    </header>
  );
}
