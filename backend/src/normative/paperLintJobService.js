const fs = require('fs');
const repository = require('./paperLintJobRepository');
const reportRepository = require('./paperLintReportRepository');
const defaultPaperLintService = require('./reviewPilotPaperLintService');
const { removeBrowserPdf } = require('./browserPdf');
const { CORE_RULE_ID, mergeCoreRuns, dedupeCorePrerequisites } = require('./paperStructureChecks');
const { jobConcurrency } = require('./paperLintConcurrency');
const {BILLABLE_RULE_IDS,beginCreditOperation,finishCreditOperation,recoverCreditOperations}=require('./paperLintCredit');

function createPaperLintJobService(paperLintService = defaultPaperLintService) {
  const queue = [];
  const queued = new Set();
  const activeRuns = new Map();
  const concurrency = jobConcurrency();
  let active = 0;

  function add(id) {
    if (queued.has(id) || activeRuns.has(id)) return;
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
    let creditContext;
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
        const envelope = job.reuse_json ? JSON.parse(job.reuse_json) : null;
        // Operator-only metadata must never become incremental report input.
        const reuse = envelope?.result ? envelope : null;
        const maxPdfBytes = envelope?.operator_options?.trusted_batch_max_pdf_bytes;
        // A restart must not rerun (and bill) a rule whose result was durably published.
        const recovered = job.attempts > 1 && job.progress_json ? JSON.parse(job.progress_json) : null;
        const recoveredIds = new Set(recovered?.completed_rule_ids || []);
        const recoveredRuns = (recovered?.rule_runs || []).filter(run => recoveredIds.has(run.rule_id));
        const reusedRuns = [...new Map([...(reuse?.result?.rule_runs || []), ...recoveredRuns]
          .map(run => [run.rule_id, run])).values()];
        const reusedIds = reusedRuns.map(run => run.rule_id);
        const pendingRuleIds = selectedRuleIds.filter(id => !reusedIds.includes(id));
        const publishProgress = progress => {
          const mergedRuns = [...[...reusedRuns, ...(progress.rule_runs || [])].reduce((runs, run) => {
            const previous = runs.get(run.rule_id);
            runs.set(run.rule_id, run.rule_id === CORE_RULE_ID && previous
              && (previous.params?.automatic_core_check || run.params?.automatic_core_check)
              ? mergeCoreRuns(previous, run) : run);
            return runs;
          }, new Map()).values()];
          const visibleRuns = dedupeCorePrerequisites(mergedRuns, selectedRuleIds);
          const visibleId = ruleId => ruleId !== CORE_RULE_ID || selectedRuleIds.includes(CORE_RULE_ID)
            || visibleRuns.some(run => run.rule_id === CORE_RULE_ID);
          return repository.updateProgress(id, {
            ...progress,
            ...(progress.document_validation?.status === 'rejected' ? {
              document_validation: { ...progress.document_validation, skipped_rule_ids: selectedRuleIds },
            } : {}),
            completed_rule_ids: progress.document_validation?.status === 'rejected' ? [] : [...new Set([...reusedIds, ...(progress.completed_rule_ids || [])])].filter(visibleId),
            total_rule_ids: [...new Set([...selectedRuleIds, ...(progress.total_rule_ids || [])])].filter(visibleId),
            rule_runs: progress.document_validation?.status === 'rejected' ? progress.rule_runs : visibleRuns,
          });
        };
        if(pendingRuleIds.some(ruleId=>BILLABLE_RULE_IDS.has(ruleId)))creditContext=await beginCreditOperation(id);
        const checked = pendingRuleIds.length ? await paperLintService.runPaperLint({
          pdfBuffer, selectedRuleIds: pendingRuleIds, externalProcessingConsent: Boolean(job.external_consent),
          background: true,
          creditContext,
          maxPdfBytes,
          trustedBatchProgress: envelope?.operator_options?.start_requested === true
            && Number.isSafeInteger(maxPdfBytes)
            && maxPdfBytes >= defaultPaperLintService.MAX_PDF_BYTES && maxPdfBytes <= 256 * 1024 * 1024,
          runId: id,
          signal: controller.signal,
          onProgress: publishProgress,
        }) : {result: {type:'paper_lint',paper_title:'上传论文',rule_runs:[],summary:{finding_count:0}}};
        if (controller.signal.aborted) return;
        const result = checked.result.document_validation?.status === 'rejected' ? {
          ...checked.result,
          document_validation: { ...checked.result.document_validation, skipped_rule_ids: selectedRuleIds },
          ...(reuse ? { incremental: { source_report_id: reuse.source_report_id,
            reused_rule_ids: [], rerun_rule_ids: [], skipped_rule_ids: selectedRuleIds } } : {}),
        } : reuse ? {
          ...defaultPaperLintService.mergePaperLintResults(
            { ...(reuse.source_report_id === null && typeof reuse.source_job_id === 'string'
              ? { ...checked.result, ...reuse.result } : reuse.result), rule_runs: reusedRuns },
            checked.result, selectedRuleIds),
          incremental: { source_report_id: reuse.source_report_id, reused_rule_ids: reusedIds, rerun_rule_ids: pendingRuleIds },
        } : recoveredRuns.length
          ? defaultPaperLintService.mergePaperLintResults({...checked.result,
            document_validation: checked.result.document_validation || recovered.document_validation,
            rule_runs: recoveredRuns}, checked.result, selectedRuleIds)
          : checked.result;
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
        if(creditContext)await finishCreditOperation(creditContext.operation_id);
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

  function drain() {
    while (active < concurrency && queue.length) {
      const id = queue.shift();
      queued.delete(id);
      active += 1;
      void process(id)
        .catch(error => { console.error('Paper-lint job worker failed:', id, error); })
        .finally(() => {
          active -= 1;
          drain();
        });
    }
  }

  async function enqueue({ userId, sourceFilename, pdfBuffer, selectedRuleIds,
                           externalProcessingConsent, requestId, reuse = null, notificationLocale }) {
    const id = await repository.createJob({
      userId, sourceFilename, pdfBuffer, selectedRuleIds, externalProcessingConsent, requestId, reuse, notificationLocale,
    });
    add(id);
    return repository.getJobForUser(id, userId);
  }

  async function enqueueIncremental({ userId, reportId, selectedRuleIds = [], externalProcessingConsent, requestId, notificationLocale }) {
    const source = await reportRepository.findPaperLintReportByIdForUser(reportId, userId);
    if (!source) throw Object.assign(new Error('未找到该审查报告'), { status: 404 });
    const allIds = [...new Set([...source.selected_rule_ids, ...selectedRuleIds])];
    const reusedRuns = source.result.rule_runs.filter(run => allIds.includes(run.rule_id)
      && (run.rule_id !== CORE_RULE_ID || source.selected_rule_ids.includes(CORE_RULE_ID))
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
      selectedRuleIds: allIds, externalProcessingConsent, requestId, notificationLocale,
      reuse: { source_report_id: reportId, result: { ...source.result, rule_runs: reusedRuns } },
    });
  }

  async function startTrustedForUser(id, userId) {
    await repository.requireTrustedBatchOwner(userId);
    const job = await repository.getJob(id);
    if (!job || job.user_id !== userId) return null;
    const envelope = job.reuse_json ? JSON.parse(job.reuse_json) : null;
    const options = envelope?.operator_options;
    if (!options || !Number.isSafeInteger(options.trusted_batch_max_pdf_bytes)
      || options.trusted_batch_max_pdf_bytes < defaultPaperLintService.MAX_PDF_BYTES
      || options.trusted_batch_max_pdf_bytes > 256 * 1024 * 1024) {
      throw Object.assign(new Error('该任务不是已预留的后台批测任务'), { status: 409 });
    }
    if (job.cancelled_at || !['pending', 'running', 'completed'].includes(job.status)) {
      throw Object.assign(new Error('该任务已结束，不能重新启动'), { status: 409 });
    }
    if (job.status === 'pending') {
      if (!options.start_requested) {
        let pdfBuffer;
        try { pdfBuffer = await fs.promises.readFile(job.source_pdf_path); }
        catch (error) {
          if (error.code === 'ENOENT') throw Object.assign(new Error('原 PDF 已不可用，无法启动'), { status: 410 });
          throw error;
        }
        paperLintService.validatePdf(pdfBuffer, options.trusted_batch_max_pdf_bytes);
        const ids = JSON.parse(job.selected_rule_ids_json);
        await paperLintService.normalizeSelectedRuleIds(ids, Boolean(job.external_consent));
        if (!(await repository.markTrustedBatchStarted(id, userId, envelope))) {
          const current = await repository.getJob(id);
          if (!current || current.cancelled_at || !['pending', 'running', 'completed'].includes(current.status)) {
            throw Object.assign(new Error('该任务已结束，不能重新启动'), { status: 409 });
          }
        }
      }
      add(id);
    }
    return repository.getJobForUser(id, userId);
  }

  async function resumeJobs() {
    await recoverCreditOperations();
    const rows = await repository.recoverJobs();
    for (const row of rows) {
      const job = await repository.getJob(row.id);
      let options;
      try { options = job?.reuse_json ? JSON.parse(job.reuse_json)?.operator_options : null; }
      catch {
        // Let the existing worker mark this one corrupt job failed.
        add(row.id);
        continue;
      }
      if (!options || options.start_requested === true) add(row.id);
    }
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

  return { enqueue, enqueueIncremental, startTrustedForUser, getForUser: repository.getJobForUser, getPdfForUser, cancelForUser, resumeJobs, waitForIdle };
}

const defaultJobService = createPaperLintJobService();
module.exports = defaultJobService;
module.exports.createPaperLintJobService = createPaperLintJobService;
