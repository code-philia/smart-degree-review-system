import express from "express";
import request from "supertest";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const authRoutes = require("../src/auth/authRoutes");
const {
  createReviewPilotPaperLintRouter,
} = require("../src/normative/reviewPilotPaperLintRoutes");
const paperLintService = require("../src/normative/reviewPilotPaperLintService");
const paperLintExampleService = require("../src/normative/paperLintExampleService");
const { createTestDatabaseHarness } = require("../src/database");

const catalog = {
  engine: "review-pilot",
  mode: "pdf_lint",
  semantic_model: "deepseek-v4-flash",
  rules: [
    {
      rule_id: "chinese_title_format_check",
      title: "中文论文题名格式",
      description: "检查中文论文题名页版式。",
      default_severity: "warning",
      default_enabled: true,
      execution_mode: "deterministic",
      uses_external_model: false,
      available: true,
    },
    {
      rule_id: "bilingual_abstract_consistency_check",
      title: "中英文摘要内容一致性",
      description: "使用 DeepSeek 检查摘要内容。",
      default_severity: "warning",
      default_enabled: false,
      execution_mode: "semantic",
      uses_external_model: true,
      available: false,
    },
  ],
};

const runResult = {
  type: "paper_lint",
  paper_title: "测试论文",
  ruleset: {
    id: "review-pilot-pdf-lint",
    name: "review-pilot PDF 规则",
    version_number: 1,
    version_label: "当前部署版本",
  },
  rule_runs: [],
  summary: {
    rule_count: 1,
    completed_rule_count: 1,
    unsupported_rule_count: 0,
    error_rule_count: 0,
    issue_rule_count: 0,
    finding_count: 0,
    error_finding_count: 0,
    warning_finding_count: 0,
    info_finding_count: 0,
    derived_rule_count: 1,
  },
};

const fakeService = {
  MAX_PDF_BYTES: paperLintService.MAX_PDF_BYTES,
  getPaperLintCatalog: vi.fn(async () => catalog),
  runPaperLint: vi.fn(async ({ selectedRuleIds }) => ({
    result: runResult,
    selectedRuleIds,
  })),
};

const exampleCase = paperLintExampleService.getPaperLintExample(
  paperLintExampleService.CLAIM_EVIDENCE_CASE_ID,
);
const bilingualAbstractCase = paperLintExampleService.getPaperLintExample(
  paperLintExampleService.BILINGUAL_ABSTRACT_CASE_ID,
);
const fakeExampleService = {
  listPaperLintExamples: vi.fn(async () =>
    paperLintExampleService.listPaperLintExamples(),
  ),
  getPaperLintExample: vi.fn(async (caseId) =>
    paperLintExampleService.getPaperLintExample(caseId),
  ),
  readPaperLintExamplePdf: vi.fn(async (caseId) => ({
    content: Buffer.from("%PDF-1.7\nbuilt-in case"),
    filename: paperLintExampleService.getPaperLintExample(caseId).pdf_filename,
  })),
};

const app = express();
app.use(express.json());
app.use("/api/auth", authRoutes);
app.use(
  "/api/normative/paper-lint",
  createReviewPilotPaperLintRouter(fakeService, fakeExampleService),
);

let harness;
const cookies = {};

describe("review-pilot paper-lint HTTP bridge", () => {
  beforeAll(async () => {
    harness = createTestDatabaseHarness({
      label: "review-pilot-paper-lint",
      seedDefault: true,
    });
    await harness.setup();
    for (const username of [
      "student01",
      "supervisor01",
      "college_admin01",
      "school_admin01",
    ]) {
      const login = await request(app)
        .post("/api/auth/login")
        .send({ username, password: "ArcDemo123!" })
        .expect(200);
      cookies[username] = login.headers["set-cookie"].find((value) =>
        value.startsWith("arc_session="),
      );
    }
  });

  afterAll(async () => harness.cleanup());

  it("denies anonymous access before loading the external engine", async () => {
    fakeService.getPaperLintCatalog.mockClear();
    await request(app).get("/api/normative/paper-lint/rules").expect(401);
    expect(fakeService.getPaperLintCatalog).not.toHaveBeenCalled();
  });

  it("returns the PDF rule catalog to every declared authenticated role", async () => {
    for (const cookie of Object.values(cookies)) {
      await request(app)
        .get("/api/normative/paper-lint/rules")
        .set("Cookie", cookie)
        .expect(200)
        .expect(catalog);
    }
  });

  it("returns the built-in case catalog to every role and protects all case resources", async () => {
    fakeExampleService.listPaperLintExamples.mockClear();
    fakeExampleService.getPaperLintExample.mockClear();
    fakeExampleService.readPaperLintExamplePdf.mockClear();

    await request(app).get("/api/normative/paper-lint/examples").expect(401);
    await request(app)
      .get(`/api/normative/paper-lint/examples/${exampleCase.id}`)
      .expect(401);
    await request(app)
      .get(`/api/normative/paper-lint/examples/${exampleCase.id}/pdf`)
      .expect(401);
    expect(fakeExampleService.listPaperLintExamples).not.toHaveBeenCalled();
    expect(fakeExampleService.getPaperLintExample).not.toHaveBeenCalled();
    expect(fakeExampleService.readPaperLintExamplePdf).not.toHaveBeenCalled();

    for (const cookie of Object.values(cookies)) {
      const response = await request(app)
        .get("/api/normative/paper-lint/examples")
        .set("Cookie", cookie)
        .expect(200);
      expect(response.body.cases).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            id: exampleCase.id,
            title: "跨页数值论点与实验论据不一致",
            claim_page: 22,
            evidence_page: 57,
            finding_count: 1,
          }),
          expect.objectContaining({
            id: bilingualAbstractCase.id,
            title: "中英文摘要研究内容不一致",
            claim_page: 7,
            evidence_page: 9,
            finding_count: 1,
          }),
        ]),
      );
    }
  });

  it("returns the deterministic case result and its matching PDF bytes", async () => {
    const detail = await request(app)
      .get(`/api/normative/paper-lint/examples/${exampleCase.id}`)
      .set("Cookie", cookies.student01)
      .expect(200);
    expect(detail.body.result.rule_runs[0]).toMatchObject({
      rule_id: "claim_evidence_inconsistency_check",
      outcome: "issues_found",
      findings: [
        {
          anchors: [
            { role: "claim", location: { page_number: 22 } },
            { role: "evidence", location: { page_number: 57 } },
          ],
        },
      ],
    });

    const pdf = await request(app)
      .get(`/api/normative/paper-lint/examples/${exampleCase.id}/pdf`)
      .set("Cookie", cookies.student01)
      .expect("Content-Type", /application\/pdf/)
      .expect(200);
    expect(pdf.body.subarray(0, 5).toString("ascii")).toBe("%PDF-");
  });

  it("returns the bilingual abstract case with Chinese and English PDF anchors", async () => {
    const detail = await request(app)
      .get(`/api/normative/paper-lint/examples/${bilingualAbstractCase.id}`)
      .set("Cookie", cookies.student01)
      .expect(200);
    expect(detail.body.result.rule_runs[0]).toMatchObject({
      rule_id: "bilingual_abstract_consistency_check",
      findings: [
        {
          anchors: [
            { role: "chinese_abstract", location: { page_number: 7 } },
            { role: "english_abstract", location: { page_number: 9 } },
          ],
        },
      ],
    });
  });

  it("passes raw PDF bytes and selected rules through without persisting a fake task", async () => {
    const pdf = Buffer.from("%PDF-1.7\nminimal test bytes");
    const response = await request(app)
      .post("/api/normative/paper-lint/run?filename=%E8%AE%BA%E6%96%87.pdf")
      .set("Cookie", cookies.student01)
      .set("Content-Type", "application/pdf")
      .set("X-Paper-Lint-Rule-Ids", "chinese_title_format_check")
      .send(pdf)
      .expect(200);

    expect(fakeService.runPaperLint).toHaveBeenCalledWith({
      pdfBuffer: expect.any(Buffer),
      selectedRuleIds: ["chinese_title_format_check"],
      externalProcessingConsent: false,
    });
    expect(
      fakeService.runPaperLint.mock.calls.at(-1)[0].pdfBuffer.equals(pdf),
    ).toBe(true);
    expect(response.body).toMatchObject({
      source_filename: "论文.pdf",
      selected_rule_ids: ["chinese_title_format_check"],
      processed_at: expect.any(String),
      result: runResult,
    });
  });

  it("passes explicit external-processing consent to the service", async () => {
    const pdf = Buffer.from("%PDF-1.7\nsemantic test bytes");
    await request(app)
      .post("/api/normative/paper-lint/run")
      .set("Cookie", cookies.student01)
      .set("Content-Type", "application/pdf")
      .set("X-Paper-Lint-Rule-Ids", "bilingual_abstract_consistency_check")
      .set("X-Paper-Lint-External-Processing-Consent", "confirmed")
      .send(pdf)
      .expect(200);

    expect(fakeService.runPaperLint).toHaveBeenLastCalledWith({
      pdfBuffer: expect.any(Buffer),
      selectedRuleIds: ["bilingual_abstract_consistency_check"],
      externalProcessingConsent: true,
    });
  });
});

describe("review-pilot PDF validation", () => {
  it("accepts a PDF signature and rejects empty or non-PDF input", () => {
    expect(() =>
      paperLintService.validatePdf(Buffer.from("%PDF-1.7\n")),
    ).not.toThrow();
    expect(() => paperLintService.validatePdf(Buffer.alloc(0))).toThrow(
      /请选择/,
    );
    expect(() =>
      paperLintService.validatePdf(Buffer.from("not a pdf")),
    ).toThrow(/有效的 PDF/);
  });

  it("rejects a semantic rule when the server has no model credential", () => {
    expect(() =>
      paperLintService.validateSelectedRuleIds(catalog, [
        "bilingual_abstract_consistency_check",
      ]),
    ).toThrow(/暂不可用/);
  });

  it("requires explicit external-processing consent for an available semantic rule", () => {
    const availableCatalog = {
      ...catalog,
      rules: catalog.rules.map((rule) => ({ ...rule, available: true })),
    };
    expect(() =>
      paperLintService.validateExternalProcessingConsent(
        availableCatalog,
        ["bilingual_abstract_consistency_check"],
        false,
      ),
    ).toThrow(/请先确认/);
    expect(() =>
      paperLintService.validateExternalProcessingConsent(
        availableCatalog,
        ["bilingual_abstract_consistency_check"],
        true,
      ),
    ).not.toThrow();
  });

  it("exposes only the declared built-in case ids", () => {
    expect(
      paperLintExampleService.listPaperLintExamples().cases.map(({ id }) => id),
    ).toEqual([
      paperLintExampleService.CLAIM_EVIDENCE_CASE_ID,
      paperLintExampleService.BILINGUAL_ABSTRACT_CASE_ID,
    ]);
    expect(() =>
      paperLintExampleService.getPaperLintExample("unknown-case"),
    ).toThrow(/不存在/);
  });
});
