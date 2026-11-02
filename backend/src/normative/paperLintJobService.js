const fs = require('fs');
const repository = require('./paperLintJobRepository');
const reportRepository = require('./paperLintReportRepository');
const defaultPaperLintService = require('./reviewPilotPaperLintService');
const { removeBrowserPdf } = require('./browserPdf');

function createPaperLintJobService(paperLintService = defaultPaperLintService) {
  const queue = [];
  const queued = new Set();
  const activeRuns = new Map();
  let active = false;

  function add(id) {
    if (queued.has(id)) return;
    queued.add(id);
    queue.push(id);
    queueMicrotask(() => { void drain(); });
  }

  async function process(id) {
    const controller = new AbortController();
    let finish;
    const finished = new Promise(resolve => { finish = resolve; });
    activeRuns.set(id, { controller, finished });
    let job;
    try {
      if (!(await repository.claimJob(id))) return;
      job = await repository.getJob(id);
      if (!job || job.cancelled_at || controller.signal.aborted) return;
      const alreadySaved = await reportRepository.findPaperLintReportByIdForUser(id, job.user_id);
      if (alreadySaved) {
        if (!(await repository.completeJob(id, id))) {
          await reportRepository.deletePaperLintReportForUser(id, job.user_id);
        }
      } else {
        const pdfBuffer = await fs.promises.readFile(job.source_pdf_path);
        const selectedRuleIds = JSON.parse(job.selected_rule_ids_json);
        const reuse = job.reuse_json ? JSON.parse(job.reuse_json) : null;
        const reusedRuns = reuse?.result?.rule_runs || [];
        const reusedIds = reusedRuns.map(run => run.rule_id);
        const pendingRuleIds = selectedRuleIds.filter(id => !reusedIds.includes(id));
        const publishProgress = progress => repository.updateProgress(id, {
          ...progress,
          completed_rule_ids: [...new Set([...reusedIds, ...(progress.completed_rule_ids || [])])],
          total_rule_ids: selectedRuleIds,
          rule_runs: [...reusedRuns, ...(progress.rule_runs || [])],
        });
        if (reuse) await publishProgress({ completed_rule_ids: [], rule_runs: [] });
        const checked = await paperLintService.runPaperLint({
          pdfBuffer, selectedRuleIds: pendingRuleIds, externalProcessingConsent: Boolean(job.external_consent),
          background: true,
          runId: id,
          signal: controller.signal,
          onProgress: publishProgress,
        });
        if (controller.signal.aborted) return;
        const result = reuse ? {
          ...defaultPaperLintService.mergePaperLintResults(reuse.result, checked.result, selectedRuleIds),
          incremental: { source_report_id: reuse.source_report_id, reused_rule_ids: reusedIds, rerun_rule_ids: pendingRuleIds },
        } : checked.result;
        await reportRepository.createPaperLintReport({
          userId: job.user_id, sourceFilename: job.source_filename, pdfBuffer,
          selectedRuleIds, result, reportId: id,
        });
        if (!(await repository.completeJob(id, id))) {
          await reportRepository.deletePaperLintReportForUser(id, job.user_id);
        }
      }
    } catch (error) {
      if (controller.signal.aborted) return;
      const message = error?.code === 'INVALID_PDF'
        ? 'PDF 文件无效或无法解析，请重新上传'
        : error?.message
          ? `检测失败，请重试：${error.message}`
          : '检测失败，请重试';
      await repository.failJob(id, message);
    } finally {
      try {
        if (job) {
          await fs.promises.rm(job.source_pdf_path, { force: true });
          await removeBrowserPdf(job.source_pdf_path);
        }
      } finally {
        activeRuns.delete(id);
        finish();
      }
    }
  }

  async function cancelForUser(id, userId) {
    const job = await repository.cancelJobForUser(id, userId);
    if (!job) return null;
    if (job.cancelled_at) {
      const activeRun = activeRuns.get(id);
      if (activeRun) {
        activeRun.controller.abort();
        await activeRun.finished;
      } else {
        await fs.promises.rm(job.source_pdf_path, { force: true });
        await removeBrowserPdf(job.source_pdf_path);
      }
    }
    return repository.getJobForUser(id, userId);
  }

  async function drain() {
    if (active) return;
    active = true;
    try {
      while (queue.length) {
        const id = queue.shift();
        queued.delete(id);
        await process(id);
      }
    } finally {
      active = false;
      if (queue.length) queueMicrotask(() => { void drain(); });
    }
  }

  async function enqueue({ userId, sourceFilename, pdfBuffer, selectedRuleIds,
                           externalProcessingConsent, requestId, reuse = null }) {
    const id = await repository.createJob({
      userId, sourceFilename, pdfBuffer, selectedRuleIds, externalProcessingConsent, requestId, reuse,
    });
    add(id);
    return repository.getJobForUser(id, userId);
  }

  async function enqueueIncremental({ userId, reportId, selectedRuleIds = [], externalProcessingConsent, requestId }) {
    const source = await reportRepository.findPaperLintReportByIdForUser(reportId, userId);
    if (!source) throw Object.assign(new Error('未找到该审查报告'), { status: 404 });
    const allIds = [...new Set([...source.selected_rule_ids, ...selectedRuleIds])];
    const reusedRuns = source.result.rule_runs.filter(run => allIds.includes(run.rule_id)
      && run.execution_status === 'completed' && run.outcome !== 'inconclusive');
    const toRun = allIds.filter(id => !reusedRuns.some(run => run.rule_id === id));
    if (!toRun.length) throw Object.assign(new Error('所选规则均已完成，请选择新增规则后再补跑'), { status: 400 });
    await paperLintService.normalizeSelectedRuleIds(toRun, externalProcessingConsent);
    const pdf = await reportRepository.getPaperLintReportPdfFile(reportId, userId);
    if (!pdf?.path) throw Object.assign(new Error('原 PDF 已不可用，无法增量补跑，请重新上传'), { status: 410 });
    let pdfBuffer;
    try { pdfBuffer = await fs.promises.readFile(pdf.path); }
    catch (error) {
      if (error.code === 'ENOENT') throw Object.assign(new Error('原 PDF 已不可用，请重新上传'), { status: 410 });
      throw error;
    }
    paperLintService.validatePdf(pdfBuffer);
    return enqueue({ userId, sourceFilename: source.source_filename, pdfBuffer,
      selectedRuleIds: allIds, externalProcessingConsent, requestId,
      reuse: { source_report_id: reportId, result: { ...source.result, rule_runs: reusedRuns } },
    });
  }

  async function resumeJobs() {
    const rows = await repository.recoverJobs();
    for (const row of rows) add(row.id);
  }

  async function waitForIdle() {
    while (active || queue.length) {
      await new Promise((resolve) => setTimeout(resolve, 10));
    }
  }

  async function getPdfForUser(id, userId) {
    const job = await repository.getJob(id);
    if (!job || job.user_id !== userId) return null;
    if (job.report_id) return reportRepository.getPaperLintReportPdfFile(job.report_id, userId);
    if (job.cancelled_at || job.status === 'failed') return { source_filename: job.source_filename, path: null };
    try {
      const stat = await fs.promises.stat(job.source_pdf_path);
      return { source_filename: job.source_filename, path: stat.isFile() ? job.source_pdf_path : null };
    } catch (error) {
      if (error.code === 'ENOENT') return { source_filename: job.source_filename, path: null };
      throw error;
    }
  }

  return { enqueue, enqueueIncremental, getForUser: repository.getJobForUser, getPdfForUser, cancelForUser, resumeJobs, waitForIdle };
}

const defaultJobService = createPaperLintJobService();
module.exports = defaultJobService;
module.exports.createPaperLintJobService = createPaperLintJobService;
