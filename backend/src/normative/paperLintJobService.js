const fs = require('fs');
const repository = require('./paperLintJobRepository');
const reportRepository = require('./paperLintReportRepository');
const defaultPaperLintService = require('./reviewPilotPaperLintService');

function createPaperLintJobService(paperLintService = defaultPaperLintService) {
  const queue = [];
  const queued = new Set();
  let active = false;

  function add(id) {
    if (queued.has(id)) return;
    queued.add(id);
    queue.push(id);
    queueMicrotask(() => { void drain(); });
  }

  async function process(id) {
    if (!(await repository.claimJob(id))) return;
    const job = await repository.getJob(id);
    if (!job) return;
    try {
      const alreadySaved = await reportRepository.findPaperLintReportByIdForUser(id, job.user_id);
      if (alreadySaved) {
        await repository.completeJob(id, id);
      } else {
        const pdfBuffer = await fs.promises.readFile(job.source_pdf_path);
        const selectedRuleIds = JSON.parse(job.selected_rule_ids_json);
        const checked = await paperLintService.runPaperLint({
          pdfBuffer, selectedRuleIds, externalProcessingConsent: Boolean(job.external_consent),
          background: true,
        });
        await reportRepository.createPaperLintReport({
          userId: job.user_id, sourceFilename: job.source_filename, pdfBuffer,
          selectedRuleIds: checked.selectedRuleIds, result: checked.result, reportId: id,
        });
        await repository.completeJob(id, id);
      }
      await fs.promises.rm(job.source_pdf_path, { force: true });
    } catch {
      await repository.failJob(id, '检测失败，请稍后重试或联系管理员');
      await fs.promises.rm(job.source_pdf_path, { force: true });
    }
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
                           externalProcessingConsent }) {
    const id = await repository.createJob({
      userId, sourceFilename, pdfBuffer, selectedRuleIds, externalProcessingConsent,
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

  return { enqueue, getForUser: repository.getJobForUser, resumeJobs, waitForIdle };
}

const defaultJobService = createPaperLintJobService();
module.exports = defaultJobService;
module.exports.createPaperLintJobService = createPaperLintJobService;

