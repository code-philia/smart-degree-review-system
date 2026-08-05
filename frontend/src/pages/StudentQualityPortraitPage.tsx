import { useState } from 'react';
import {
  StudentQualityPortraitResponse,
  fetchStudentQualityPortrait,
} from '../api/normativeRules';

function formatPortraitScore(score: number | null) {
  return score === null ? '数据不完整' : `${score.toFixed(1)} 分`;
}

function StudentQualityPortraitPage() {
  const [studentId, setStudentId] = useState('');
  const [portrait, setPortrait] = useState<StudentQualityPortraitResponse | null>(null);
  const [status, setStatus] = useState<'idle' | 'loading' | 'error'>('idle');
  const [errorMessage, setErrorMessage] = useState('');

  async function loadPortrait() {
    if (!studentId.trim()) {
      setStatus('error');
      setErrorMessage('请输入学生画像 ID');
      return;
    }
    setStatus('loading');
    setErrorMessage('');
    try {
      const nextPortrait = await fetchStudentQualityPortrait(studentId.trim());
      setPortrait(nextPortrait);
      setStatus('idle');
    } catch (error) {
      setStatus('error');
      setErrorMessage(error instanceof Error ? error.message : '单学生质量画像加载失败');
    }
  }

  return (
    <main className="min-h-screen bg-[#f5f8fb] text-[#1f2d3d]">
      <header className="flex h-[56px] items-center justify-center bg-[#1f3f63] text-[22px] font-bold text-white">
        单学生本地质量画像
      </header>
      <section className="mx-7 mt-5 flex flex-wrap items-end gap-3 border border-[#d9e1ea] bg-[#eef5fb] p-4">
        <label className="grid gap-2 text-sm font-semibold text-[#1f3f63]">
          学生画像 ID
          <input className="h-10 min-w-[240px] border border-[#d9e1ea] bg-white px-3 font-normal" value={studentId} onChange={(event) => setStudentId(event.target.value)} placeholder="学生本人或组织范围内学生 ID" />
        </label>
        <button className="h-10 bg-[#2f80ed] px-8 font-bold text-white" type="button" onClick={() => void loadPortrait()}>查询</button>
      </section>

      {status === 'loading' && <p className="py-16 text-center text-[#536476]">质量画像加载中...</p>}
      {status === 'error' && <p className="py-16 text-center text-red-600">{errorMessage}</p>}
      {status === 'idle' && !portrait && <p className="py-16 text-center text-[#536476]">请输入学生 ID 后查看该学生最新完成记录画像</p>}

      {portrait && (
        <section className="mx-7 my-5 overflow-hidden border border-[#d9e1ea] bg-white">
          <h2 className="bg-[#1f3f63] px-5 py-3 text-lg font-bold text-white">单学生论文全景质量画像</h2>
          <div className="grid gap-5 p-5 lg:grid-cols-[1.15fr_0.85fr]">
            <div className="space-y-4">
              <div className="grid gap-3 rounded border border-[#d9e1ea] bg-[#eaf4ff] p-4 md:grid-cols-3">
                <p><span className="text-[#536476]">学号：</span><strong>{portrait.student.student_number}</strong></p>
                <p><span className="text-[#536476]">姓名：</span><strong>{portrait.student.student_name}</strong></p>
                <p><span className="text-[#536476]">学院：</span><strong>{portrait.student.college_name}</strong></p>
                <p><span className="text-[#536476]">导师：</span><strong>{portrait.student.supervisor_name || '暂无'}</strong></p>
                <p className="md:col-span-2"><span className="text-[#536476]">论文：</span><strong>{portrait.student.thesis_title || '暂无最新论文题目'}</strong></p>
              </div>
              <div className="grid gap-3 md:grid-cols-5">
                {portrait.metrics.map((metric) => (
                  <article key={metric.key} className="rounded border border-[#d9e1ea] bg-white p-4 text-center">
                    <p className="text-sm text-[#536476]">{metric.label}</p>
                    <strong className="text-2xl text-[#1f3f63]">{metric.score === null ? '缺失' : metric.score.toFixed(1)}</strong>
                    <p className="mt-2 text-xs text-[#536476]">{metric.source_created_at || '暂无完成记录'}</p>
                    {metric.detail_url && <a className="text-sm font-semibold text-[#2f80ed]" href={metric.detail_url}>查看详情</a>}
                  </article>
                ))}
              </div>
              <article className="rounded border border-[#d9e1ea] bg-[#f8fafc] p-4">
                <p className="text-[#536476]">综合分</p>
                <strong className="text-3xl text-[#19a85b]">{formatPortraitScore(portrait.overall_score)}</strong>
                {!portrait.completeness.complete && <p className="mt-2 text-[#f39a2e]">缺失项：{portrait.completeness.missing_metric_labels.join('、')}</p>}
              </article>
            </div>
            <article className="rounded border border-[#d9e1ea] bg-white p-5">
              <h3 className="mb-4 text-center text-lg font-bold text-[#1f3f63]">四指标雷达图</h3>
              <div className="grid place-items-center rounded bg-[#f8fbff] py-12 text-[#536476]">
                后续实现按返回 metrics 渲染运行时雷达图
              </div>
            </article>
          </div>
        </section>
      )}
    </main>
  );
}

export default StudentQualityPortraitPage;
