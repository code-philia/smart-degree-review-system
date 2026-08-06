import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  downloadAiReviewResultJson,
  fetchAiReviewResult,
  type AiReviewResultResponse,
} from '../api/normativeRules';
import { useAuthSession } from '../auth/AuthSessionProvider';
import { Card, EmptyState, ErrorState, LinkButton, LoadingState, PageHeader } from '../components/ui';

function formatTimestamp(value: string) {
  return value ? value.replace('T', ' ').replace('Z', '') : '—';
}

function buildLineRows(text: string) {
  return text.split(/\r?\n/).map((line, index) => ({ lineNumber: index + 1, text: line || ' ' }));
}

function AiReviewResultPage() {
  const { reviewRunId } = useParams<{ reviewRunId: string }>();
  const { status, user } = useAuthSession();
  const [result, setResult] = useState<AiReviewResultResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const previewLines = useMemo(() => (result ? buildLineRows(result.original_text) : []), [result]);
  const scoreSum = useMemo(
    () => result?.score_items.reduce((sum, item) => sum + Number(item.score || 0), 0) ?? 0,
    [result],
  );

  useEffect(() => {
    if (status !== 'authenticated' || !user || !reviewRunId) {
      return;
    }

    let cancelled = false;
    setLoading(true);
    setErrorMessage(null);
    setResult(null);

    fetchAiReviewResult(reviewRunId)
      .then((nextResult) => {
        if (!cancelled) {
          setResult(nextResult);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setErrorMessage(error instanceof Error ? error.message : '辅助评阅结果加载失败');
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [reviewRunId, status, user]);

  async function handleDownloadJson() {
    if (!reviewRunId || !result) {
      return;
    }

    const blob = await downloadAiReviewResultJson(reviewRunId);
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `ai-review-result-${reviewRunId}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  if (status === 'loading') {
    return <LoadingState label="正在加载登录状态…" />;
  }

  if (!user) {
    return (
      <div className="mx-auto max-w-4xl">
        <Card>
          <h1 className="text-center text-[28px] font-black text-[#1F3D5F]">AI 智能评阅报告</h1>
          <p className="mt-4 text-center text-slate-600">请先登录后查看已完成的辅助评阅结果。</p>
          <div className="mt-6 flex justify-center">
            <LinkButton to="/auth">前往登录</LinkButton>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="font-['Microsoft_YaHei','PingFang_SC','Noto_Sans_SC',Arial,sans-serif] text-[#1F2D3D]">
      <PageHeader title="AI 智能评阅报告" />

      <section className="grid min-h-[70vh] grid-cols-[40%_60%] border border-[#D8D8D8] shadow-sm">
        <aside className="flex min-h-0 flex-col border-r border-[#D8D8D8] bg-[#F2F2F2]">
          <h2 className="flex h-[45px] items-center justify-center bg-[#203B5A] text-[17px] font-black text-white">📄 论文预览</h2>
          <div className="flex h-11 items-center justify-center border-b border-[#D8D8D8] bg-white px-4 text-sm font-bold">
            {result?.source_filename || result?.thesis_title || '—'}
          </div>
          <div className="min-h-0 flex-1 overflow-auto p-5">
            <pre className="min-h-full whitespace-pre-wrap border border-[#D8D8D8] bg-white p-5 text-[13px] leading-6 text-slate-800">
              {previewLines.map((line) => (
                <span key={line.lineNumber} className="block">
                  <span className="mr-4 inline-block w-10 select-none border-r border-[#E3E3E3] pr-3 text-right text-slate-400">{line.lineNumber}</span>
                  <span>{line.text}</span>
                </span>
              ))}
            </pre>
          </div>
          <div className="flex h-12 items-center justify-center gap-2 border-t border-[#D8D8D8] bg-white text-xs text-slate-600 print:hidden">
            <button className="rounded border border-[#D8D8D8] px-3 py-1" type="button" disabled>−</button>
            <span className="rounded border border-[#D8D8D8] px-3 py-1">100%</span>
            <button className="rounded border border-[#D8D8D8] px-3 py-1" type="button" disabled>＋</button>
            <span className="mx-2 h-5 border-l border-[#D8D8D8]" />
            <span className="rounded border border-[#D8D8D8] px-3 py-1">纯文本预览</span>
          </div>
        </aside>

        <section className="min-h-0 overflow-y-auto bg-white p-4">
          <div className="mb-4 flex justify-end gap-3 print:hidden">
            <button className="rounded bg-[#42B35A] px-5 py-3 text-sm font-black text-white disabled:opacity-50" type="button" disabled={!result} onClick={handleDownloadJson}>下载 JSON</button>
            <button className="rounded border border-[#203B5A] px-5 py-3 text-sm font-black text-[#203B5A]" type="button" onClick={() => window.print()}>浏览器打印</button>
          </div>

          {loading ? <LoadingState label="正在加载辅助评阅结果…" /> : null}
          {errorMessage ? <ErrorState message={errorMessage} /> : null}
          {!loading && !errorMessage && !result ? <EmptyState title="暂无可展示的辅助评阅结果。" /> : null}

          {result ? (
            <div className="space-y-4 text-[13px]">
              <section className="border border-[#D8D8D8]">
                <h2 className="bg-[#203B5A] py-2 text-center text-[17px] font-black text-white">一、评阅基本信息</h2>
                <table className="w-full border-collapse">
                  <tbody>
                    {[
                      ['论文题目', result.thesis_title],
                      ['评阅模板', result.template_id],
                      ['文本来源', result.source_type === 'file' ? '文件上传' : '文本粘贴'],
                      ['字符数', String(result.character_count)],
                      ['参考文献数量', String(result.reference_count)],
                      ['生成时间', formatTimestamp(result.created_at)],
                    ].map(([label, value]) => (
                      <tr key={label} className="border-t border-[#E3E3E3]">
                        <th className="w-36 bg-[#F7F7F7] px-3 py-2 text-left font-bold">{label}</th>
                        <td className="px-3 py-2 font-bold">{value || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>

              <section className="border border-[#D8D8D8]">
                <h2 className="bg-[#203B5A] py-2 text-center text-[17px] font-black text-white">二、客观检查项</h2>
                <table className="w-full border-collapse">
                  <thead className="bg-[#203B5A] text-white">
                    <tr>
                      <th className="border border-[#E3E3E3] px-2 py-2">检查项</th>
                      <th className="border border-[#E3E3E3] px-2 py-2">分值</th>
                      <th className="border border-[#E3E3E3] px-2 py-2">得分</th>
                      <th className="border border-[#E3E3E3] px-2 py-2">发现</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.score_items.map((item) => (
                      <tr key={item.key}>
                        <td className="border border-[#E3E3E3] px-2 py-2 font-bold">{item.label}</td>
                        <td className="border border-[#E3E3E3] px-2 py-2 text-center">{item.points}</td>
                        <td className="border border-[#E3E3E3] bg-[#EAF8EC] px-2 py-2 text-center text-lg font-black text-[#278A3E]">{item.score}</td>
                        <td className="border border-[#E3E3E3] px-2 py-2">{item.findings.length ? item.findings.join('；') : '未发现扣分项'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="border-t border-[#D8D8D8] bg-[#EAF8EC] px-4 py-3 text-center font-bold text-[#278A3E]">
                  五项得分合计 <span className="text-2xl">{scoreSum}</span> / 系统总分 <span className="text-2xl">{result.total_score}</span> · 结论：{result.result_label}
                </div>
              </section>

              <section className="border border-[#D8D8D8]">
                <h2 className="bg-[#203B5A] py-2 text-center text-[17px] font-black text-white">三、规范问题与人工确认</h2>
                <div className="grid gap-3 p-3">
                  <div className="rounded border border-[#F28C28] bg-[#FFF4EA] p-3">
                    <h3 className="font-black text-[#B85F00]">规范问题</h3>
                    <p className="mt-2">{result.normative_issues.length ? result.normative_issues.map((issue) => issue.message).join('；') : '未发现规范问题'}</p>
                  </div>
                  <div className="rounded border border-[#2F86F6] bg-[#EEF6FF] p-3">
                    <h3 className="font-black text-[#1D65C1]">主观学术维度</h3>
                    <ul className="mt-2 grid gap-1">
                      {result.subjective_confirmation_items.map((item) => (
                        <li key={item.key}>{item.label}：<span className="font-black">{item.status}</span></li>
                      ))}
                    </ul>
                  </div>
                </div>
              </section>
            </div>
          ) : null}
        </section>
      </section>
    </div>
  );
}

export default AiReviewResultPage;
