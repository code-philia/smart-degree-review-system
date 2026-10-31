import { PAGE, paginateReportSteps } from './layout';
import { reportBlocks, type ExportReport } from './model';

const FONT = '"Microsoft YaHei","PingFang SC","Noto Sans CJK SC",sans-serif';
export type ExportProgress = (message: string) => void;
export function checkCancelled(signal?: AbortSignal) {
  if (signal?.aborted) throw new DOMException('已取消导出', 'AbortError');
}
export async function* renderReportPages(model: ExportReport, signal?: AbortSignal, onProgress?: ExportProgress) {
  checkCancelled(signal);
  await document.fonts?.ready;
  const canvas = document.createElement('canvas');
  canvas.width = PAGE.pageWidth;
  canvas.height = PAGE.pageHeight;
  const context = canvas.getContext('2d');
  if (!context) throw new Error('当前浏览器无法生成图片，请选择 Word、Markdown、文本或 JSON。');
  try {
    onProgress?.('正在排版报告');
    const steps = paginateReportSteps(reportBlocks(model), (text, size, bold) => {
      context.font = `${bold ? 600 : 400} ${size}px ${FONT}`;
      return context.measureText(text).width;
    });
    let layout = steps.next();
    while (!layout.done) {
      await new Promise<void>((resolve) => setTimeout(resolve, 0));
      checkCancelled(signal);
      layout = steps.next();
    }
    const pages = layout.value;
    for (let index = 0; index < pages.length; index++) {
      checkCancelled(signal);
      onProgress?.(`正在生成第 ${index + 1} / ${pages.length} 页`);
      context.fillStyle = '#ffffff';
      context.fillRect(0, 0, canvas.width, canvas.height);
      context.textBaseline = 'top';
      context.fillStyle = '#28486d';
      context.fillRect(PAGE.margin, 66, 38, 4);
      context.font = `500 19px ${FONT}`;
      context.fillText('智慧学位 · AI 评阅辅助系统', PAGE.margin + 52, 57);
      context.strokeStyle = '#e1e7ef';
      context.lineWidth = 1;
      context.beginPath();
      context.moveTo(PAGE.margin, 105);
      context.lineTo(canvas.width - PAGE.margin, 105);
      context.stroke();
      for (const line of pages[index].lines) {
        context.font = `${line.bold ? 600 : 400} ${line.fontSize}px ${FONT}`;
        context.fillStyle = line.color;
        context.fillText(line.text, PAGE.margin + line.indent, line.y);
      }
      context.font = `400 18px ${FONT}`;
      context.fillStyle = '#718096';
      context.fillText('检测结果仅供参考', PAGE.margin, canvas.height - 58);
      const label = `${index + 1} / ${pages.length}`;
      context.fillText(label, canvas.width - PAGE.margin - context.measureText(label).width, canvas.height - 58);
      yield { canvas, index, total: pages.length };
      await new Promise<void>((resolve) => setTimeout(resolve, 0));
    }
  } finally {
    canvas.width = 1;
    canvas.height = 1;
  }
}
export function canvasPng(canvas: HTMLCanvasElement) {
  return new Promise<Blob>((resolve, reject) =>
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('图片生成失败，请重试。'))), 'image/png'),
  );
}
