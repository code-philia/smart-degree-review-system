import { PageHeader, Card } from '../components/ui';

const AVAILABLE_CAPABILITIES = [
  { title: '论文规范性检测', text: '按当前生效规则检查章节顺序、标点配对、参考文献和禁用词等问题，并定位到具体行列。' },
  {
    title: 'PDF 语义规则审查',
    text: '服务器配置模型密钥后，可按需使用 DeepSeek 检查中英文摘要一致性、数值论点与论据矛盾及强论断支撑；只发送规则选中的相关文本，结果必须人工复核。',
  },
  { title: '论文相似度检测', text: '与试点样本库中的文本进行片段比对，给出相似段落和写作风险提示。' },
  { title: '创新性量表评估', text: '按硕士/博士五维度量表录入证据，计算创新性参考分。' },
  { title: '规则化辅助评阅', text: '基于内置评阅模板检查必需章节、参考文献数量等客观项，生成参考评分。' },
  { title: '论文润色', text: '生成整篇或局部的规则改写建议，并保留修改前后对比。' },
  { title: '师生报告流转', text: '学生可将已完成报告提交给导师，导师在站内批阅并反馈结果。' },
  { title: '检测台账与质量看板', text: '按角色数据范围查看检测记录、统计趋势和论文质量画像。' },
];

const UNAVAILABLE_CAPABILITIES = [
  { title: '统一身份认证', text: '暂未接入 jAccount、短信验证码或微信扫码登录，当前使用账号密码方式登录。' },
  {
    title: '通用大模型能力',
    text: '外部模型目前只用于 3 条明确标注的 PDF 语义规则；润色、创新性评估和辅助评阅仍由本地规则与公式计算。',
  },
  { title: '真实论文库比对', text: '相似度检测基于试点样本库比对，暂未接入校内外正式论文库。' },
  {
    title: 'Word / PDF 深度解析',
    text: '当前支持 .txt、.md 和含可搜索文字层的 PDF；暂不支持 Word、扫描或加密 PDF，也不解析字体、页边距、页眉页脚和页面坐标。',
  },
  { title: '微服务与私有云部署', text: '当前为单体应用试点部署，暂未进行微服务拆分和校内私有云对接。' },
];

function CapabilityList({ items, tone }: { items: typeof AVAILABLE_CAPABILITIES; tone: 'available' | 'unavailable' }) {
  return (
    <ul className="space-y-3">
      {items.map((item) => (
        <li key={item.title} className="flex gap-3 rounded-lg border border-slate-100 bg-slate-50 p-3">
          <span
            className={`mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-xs font-black text-white ${
              tone === 'available' ? 'bg-success-600' : 'bg-slate-400'
            }`}
            aria-hidden="true"
          >
            {tone === 'available' ? '✓' : '·'}
          </span>
          <div>
            <p className="text-sm font-bold text-slate-800">{item.title}</p>
            <p className="mt-1 text-sm leading-6 text-slate-500">{item.text}</p>
          </div>
        </li>
      ))}
    </ul>
  );
}

function AboutPage() {
  return (
    <div>
      <PageHeader
        title="系统说明"
        description="智慧学位 AI 评阅辅助系统目前处于试点验证阶段，用于让相关老师和同学提前体验核心流程并给出反馈，尚未按照正式生产系统的标准全面上线。"
      />

      <div className="grid gap-5 xl:grid-cols-2">
        <Card title="当前已提供的能力">
          <CapabilityList items={AVAILABLE_CAPABILITIES} tone="available" />
        </Card>
        <Card title="尚未接入的能力">
          <CapabilityList items={UNAVAILABLE_CAPABILITIES} tone="unavailable" />
        </Card>
      </div>

      <Card className="mt-5" title="数据范围说明">
        <p className="text-sm leading-6 text-slate-600">
          试点版本中的检测、评分和统计数据来自试点期间录入和生成的真实运行数据，不使用编造的示例数据；相似度检测所依据的比对样本库范围有限，仅覆盖试点阶段导入的样本，尚不能代表全校正式论文库。
        </p>
      </Card>

      <Card className="mt-5" title="试用账号">
        <p className="text-sm leading-6 text-slate-600">
          试点阶段面向学生、导师、学院管理人员和学校管理人员各提供一个试用账号，用于体验不同角色的操作界面。账号详情可在登录页的“试用账号”区域查看。
        </p>
      </Card>
    </div>
  );
}

export default AboutPage;
