import { useEffect, useState } from 'react';
import { fetchReviewRubrics, type ReviewRubricsResponse } from '../api/normativeRules';

type ReviewRubricSelectorProps = {
  isOpen: boolean;
};

function ReviewRubricSelector({ isOpen }: ReviewRubricSelectorProps) {
  const [rubrics, setRubrics] = useState<ReviewRubricsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen || rubrics) {
      return;
    }

    let mounted = true;
    setLoading(true);
    setErrorMessage(null);

    const timer = window.setTimeout(() => {
      Promise.allSettled([
        fetchReviewRubrics(),
        new Promise((resolve) => window.setTimeout(resolve, 80)),
      ]).then(([rubricResult]) => {
        if (!mounted) {
          return;
        }

        if (rubricResult.status === 'fulfilled') {
          setRubrics(rubricResult.value);
        } else {
          const error = rubricResult.reason;
          setErrorMessage(error instanceof Error ? error.message : '评阅模板加载失败');
        }
        setLoading(false);
      });
    }, 0);

    return () => {
      mounted = false;
      window.clearTimeout(timer);
    };
  }, [isOpen, rubrics]);

  if (!isOpen) {
    return null;
  }

  if (loading) {
    return <p className="mt-4 rounded-2xl border border-blue-100 bg-blue-50 px-4 py-3 text-sm font-semibold text-blue-700">正在加载评阅模板…</p>;
  }

  if (errorMessage) {
    return <p className="mt-4 rounded-2xl border border-red-100 bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">{errorMessage}</p>;
  }

  if (!rubrics) {
    return <p className="mt-4 rounded-2xl border border-dashed border-slate-200 px-4 py-3 text-sm text-slate-500">打开后将从后端加载内置评阅模板。</p>;
  }

  return (
    <div className="mt-4 space-y-4">
      <div className="grid gap-3 lg:grid-cols-2">
        {rubrics.templates.map((template) => (
          <article key={template.template_id} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <h3 className="font-black text-slate-900">{template.name}</h3>
            <p className="mt-2 text-sm font-semibold text-blue-700">最低参考文献数量：{template.minimum_reference_count}</p>
            <p className="mt-3 text-xs font-bold text-slate-500">必需章节</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {template.required_sections.map((section) => (
                <span key={section} className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700">{section}</span>
              ))}
            </div>
          </article>
        ))}
      </div>

      <section className="rounded-2xl border border-blue-100 bg-blue-50 p-4">
        <h3 className="font-black text-slate-900">共享客观计分项</h3>
        <div className="mt-3 grid gap-2 md:grid-cols-5">
          {rubrics.shared_score_items.map((item) => (
            <div key={item.key} className="rounded-xl bg-white px-3 py-2 text-center shadow-sm">
              <p className="text-xs font-semibold text-slate-500">{item.label}</p>
              <p className="mt-1 text-lg font-black text-blue-700">{item.points} 分</p>
            </div>
          ))}
        </div>
        <div className="mt-3 flex flex-wrap gap-2 text-sm font-semibold">
          <span className="rounded-full bg-emerald-100 px-3 py-1 text-emerald-700">{rubrics.passing_rule.pass_label}</span>
          <span className="rounded-full bg-amber-100 px-3 py-1 text-amber-700">{rubrics.passing_rule.revise_label}</span>
        </div>
        <p className="mt-3 text-sm font-semibold text-slate-700">
          客观分不低于 {rubrics.passing_rule.minimum_objective_score} 且无必需章节缺失时为“{rubrics.passing_rule.pass_label}”，否则为“{rubrics.passing_rule.revise_label}”。
        </p>
      </section>
    </div>
  );
}

export default ReviewRubricSelector;
