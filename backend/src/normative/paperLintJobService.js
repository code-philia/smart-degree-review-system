const fs = require('fs');
const repository = require('./paperLintJobRepository');
const reportRepository = require('./paperLintReportRepository');
const defaultPaperLintService = require('./reviewPilotPaperLintService');

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
        const checked = await paperLintService.runPaperLint({
          pdfBuffer, selectedRuleIds, externalProcessingConsent: Boolean(job.external_consent),
          background: true,
          runId: id,
          signal: controller.signal,
          onProgress: (progress) => repository.updateProgress(id, progress),
        });
        if (controller.signal.aborted) return;
        await reportRepository.createPaperLintReport({
          userId: job.user_id, sourceFilename: job.source_filename, pdfBuffer,
          selectedRuleIds: checked.selectedRuleIds, result: checked.result, reportId: id,
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
        if (job) await fs.promises.rm(job.source_pdf_path, { force: true });
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
                           externalProcessingConsent, requestId }) {
    const id = await repository.createJob({
      userId, sourceFilename, pdfBuffer, selectedRuleIds, externalProcessingConsent, requestId,
    });
    add(id);
    return repository.getJobForUser(id, userId);
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

  return { enqueue, getForUser: repository.getJobForUser, cancelForUser, resumeJobs, waitForIdle };
}

const defaultJobService = createPaperLintJobService();
module.exports = defaultJobService;
module.exports.createPaperLintJobService = createPaperLintJobService;
