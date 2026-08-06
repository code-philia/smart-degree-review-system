import { useState, type ChangeEvent, type FormEvent } from 'react';
import { importRuleDraftTemplate, type ImportRuleDraftTemplateResponse } from '../api/ruleConfig';

const MAX_RULE_DRAFT_IMPORT_BYTES = 1024 * 1024;

function RuleDraftImportPanel() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isImporting, setIsImporting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [result, setResult] = useState<ImportRuleDraftTemplateResponse | null>(null);

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] || null;
    setSelectedFile(file);
    setResult(null);
    setErrorMessage(null);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedFile) {
      setErrorMessage('请选择 UTF-8 JSON 规则集文件');
      return;
    }
    if (selectedFile.size > MAX_RULE_DRAFT_IMPORT_BYTES) {
      setErrorMessage('文件大小不能超过 1 MB');
      return;
    }

    setIsImporting(true);
    setErrorMessage(null);
    try {
      const response = await importRuleDraftTemplate(selectedFile);
      setResult(response);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '规则草稿导入失败');
    } finally {
      setIsImporting(false);
    }
  }

  return (
    <section className="border-t border-[#D8DDE6]">
      <div className="bg-[#243E66] px-5 py-3 text-lg font-bold text-white">JSON 规则集导入草稿</div>
      <form className="space-y-4 p-5" onSubmit={handleSubmit}>
        <p className="text-sm leading-6 text-slate-600">
          上传不超过 1 MB 的 UTF-8 JSON 数组文件，仅保存为规则草稿，不会自动生效；DOC/DOCX 模板不支持自动推导规则。
        </p>
        <input
          accept="application/json,.json"
          className="block w-full rounded-lg border border-[#D8DDE6] p-3 text-sm"
          name="ruleDraftTemplate"
          onChange={handleFileChange}
          type="file"
        />
        {errorMessage ? <p className="text-sm font-semibold text-red-600">{errorMessage}</p> : null}
        {result ? (
          <p className="text-sm font-semibold text-green-700">
            已创建 {result.imported_count} 条规则草稿，未改变已生效规则。
          </p>
        ) : null}
        <button
          className="rounded-lg bg-[#3D8BFF] px-5 py-2 text-sm font-bold text-white disabled:opacity-50"
          disabled={isImporting}
          type="submit"
        >
          {isImporting ? '正在导入…' : '导入规则草稿'}
        </button>
      </form>
    </section>
  );
}

export default RuleDraftImportPanel;
