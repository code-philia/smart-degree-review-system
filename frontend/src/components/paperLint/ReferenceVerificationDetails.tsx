/** @jsxImportSource react */
import { useId, useSyncExternalStore } from 'react';
import { ArrowUpRight, CheckCircle2, ChevronRight, MapPin } from 'lucide-react';
import { getLocale, subscribe } from '../../i18n/locale';
import type {
  ReferenceVerificationCategory,
  ReferenceVerificationEntry,
  ReferenceVerificationSummary,
} from '../../api/paperLint';
import './reference-verification-details.css';

const categories: ReferenceVerificationCategory[] = [
  'verified',
  'suspected',
  'mismatch',
  'upgrade',
  'incomplete',
  'unverified',
];
const labels = {
  zh: {
    verified: '已核验',
    suspected: '疑似伪造',
    mismatch: '信息不符',
    upgrade: '可升级',
    incomplete: '可补全',
    unverified: '未核验',
  },
  en: {
    verified: 'Verified',
    suspected: 'Suspected fabrication',
    mismatch: 'Metadata mismatch',
    upgrade: 'Published version available',
    incomplete: 'Can be completed',
    unverified: 'Unverified',
  },
};
const copy = {
  zh: {
    original: '参考文献原文',
    noText: '未可靠提取到参考文献原文。',
    cited: '原引用',
    matched: '数据库记录',
    sources: '核验来源',
    fields: (n: number) => `字段比较（${n}）`,
    noSources: '暂无可展示的数据库来源。',
    openDoi: '打开 DOI',
    baiduScholar: '百度学术',
    relatedLinks: '文献检索',
    fieldLabel: '字段',
    summary: '参考文献核验概览',
    processed: (n: number) => `已处理 ${n} 条`,
    verifiedEntries: (n: number) => `已核验条目（${n}）`,
    native: '基于 PDF 原生文字提取',
    jumpToPage: (page: number) => `跳到 PDF 第 ${page} 页`,
    advice: {
      verified: '标识符或文献元数据已得到来源支持。',
      suspected: '公开检索未找到充分匹配，不代表文献一定不存在，请对照原始来源人工复核。',
      mismatch: '请对照数据库记录及原始文献，核对不一致的字段。',
      upgrade: '发现相关正式出版版本，请核对实际引用的版本后决定是否更新。',
      incomplete: '可对照数据库记录补全缺失信息。',
      unverified: '当前信息或检索覆盖不足。未核验不表示引用存在问题，请人工核对。',
    },
    reason: {
      identifier_verified: '标识符匹配',
      metadata_verified: '文献元数据匹配',
      metadata_conflict: '文献信息不一致',
      identifier_conflict: '标识符与文献信息不一致',
      publication_available: '发现正式出版版本',
      missing_doi: '可补充 DOI',
      incomplete_extraction: '原文提取信息不足',
      bibliography_not_extracted: '未可靠识别参考文献列表',
      provider_unavailable: '数据源暂不可用',
      outside_database_coverage: '数据库覆盖不足',
      incomplete_catalog_metadata: '数据库元数据不足',
      not_found_in_checked_databases: '当前数据库检索未找到充分匹配',
      ambiguous_catalog_candidates: '候选记录尚不能确认',
      supplemental_search_unresolved: '补充检索仍未确认',
      insufficient_evidence: '核验依据不足',
    },
    field: { title: '题名', authors: '作者', year: '年份', doi: 'DOI', arxiv_id: 'arXiv' },
    status: {
      match: '一致',
      different: '不一致',
      equivalent: '相关版本',
      missing: '缺失',
      unknown: '待核查',
      success: '已检索',
      not_found: '未匹配',
      unavailable: '不可用',
      timeout: '超时',
      rate_limited: '额度或频率受限',
      unauthorized: '授权不可用',
    },
  },
  en: {
    original: 'Original reference',
    noText: 'The original reference could not be reliably extracted.',
    cited: 'Original citation',
    matched: 'Database record',
    sources: 'Verification sources',
    fields: (n: number) => `Compare fields (${n})`,
    noSources: 'No database sources are available to display.',
    openDoi: 'Open DOI',
    baiduScholar: 'Baidu Scholar',
    relatedLinks: 'Reference links',
    fieldLabel: 'Field',
    summary: 'Reference verification summary',
    processed: (n: number) => `${n} ${n === 1 ? 'reference' : 'references'} processed`,
    verifiedEntries: (n: number) => `Verified references (${n})`,
    native: 'Extracted from native PDF text',
    jumpToPage: (page: number) => `Jump to PDF page ${page}`,
    advice: {
      verified: 'The identifier or reference metadata is supported by the sources.',
      suspected:
        'Public searches did not establish a sufficient match. This does not prove nonexistence; review the original source.',
      mismatch: 'Check the differing fields against the database record and original publication.',
      upgrade: 'A related published version is available. Review the version actually cited before updating.',
      incomplete: 'Complete missing fields using the database record.',
      unverified:
        'The available metadata or search coverage is insufficient. An unverified result does not establish a citation error; review manually.',
    },
    reason: {
      identifier_verified: 'Identifier matched',
      metadata_verified: 'Reference metadata matched',
      metadata_conflict: 'Reference metadata differs',
      identifier_conflict: 'Identifier and metadata conflict',
      publication_available: 'Published version found',
      missing_doi: 'DOI can be added',
      incomplete_extraction: 'Insufficient extracted metadata',
      bibliography_not_extracted: 'Bibliography could not be reliably extracted',
      provider_unavailable: 'Source temporarily unavailable',
      outside_database_coverage: 'Outside database coverage',
      incomplete_catalog_metadata: 'Incomplete catalog metadata',
      not_found_in_checked_databases: 'No sufficient match in checked databases',
      ambiguous_catalog_candidates: 'Catalog candidates are inconclusive',
      supplemental_search_unresolved: 'Supplemental search remains inconclusive',
      insufficient_evidence: 'Insufficient verification evidence',
    },
    field: { title: 'Title', authors: 'Authors', year: 'Year', doi: 'DOI', arxiv_id: 'arXiv' },
    status: {
      match: 'Match',
      different: 'Different',
      equivalent: 'Related version',
      missing: 'Missing',
      unknown: 'Needs review',
      success: 'Searched',
      not_found: 'No match',
      unavailable: 'Unavailable',
      timeout: 'Timed out',
      rate_limited: 'Quota or rate limited',
      unauthorized: 'Authorization unavailable',
    },
  },
};

function valueText(value: unknown): string {
  if (Array.isArray(value))
    return value.filter((part) => typeof part === 'string' || typeof part === 'number').join('; ') || '—';
  return (typeof value === 'string' && value.trim()) || typeof value === 'number' ? String(value) : '—';
}
function doiLink(value?: string | null) {
  if (typeof value !== 'string') return null;
  try {
    const doi = decodeURIComponent(value.trim().replace(/^(?:doi:\s*|https?:\/\/(?:dx\.)?doi\.org\/)/i, ''));
    if (!/^10\.\d{4,9}\/[^\s"\\]+$/i.test(doi) || doi.length > 512) return null;
    return `https://doi.org/${doi.split('/').map(encodeURIComponent).join('/')}`;
  } catch { return null; }
}
function useCopy() {
  const locale = useSyncExternalStore(subscribe, getLocale, getLocale);
  const language = locale === 'en' ? 'en' : 'zh';
  return { text: copy[language], tags: labels[language] };
}

export function ReferenceVerificationDetails({ check, onNavigate }: { check: ReferenceVerificationEntry; onNavigate?: () => void }) {
  const { text, tags } = useCopy();
  const category = categories.includes(check.category) ? check.category : 'unverified';
  const reason = text.reason[check.reason_code as keyof typeof text.reason] || text.advice[category];
  const comparisons = Array.isArray(check.comparisons) ? check.comparisons : [];
  const original = (
    check.entry?.text ||
    [check.entry?.title, check.entry?.authors?.join('; '), check.entry?.year, check.entry?.doi || check.entry?.arxiv_id]
      .filter(Boolean)
      .join(' · ')).replace(/\s+/g, ' ').trim();
  const page = check.entry?.location?.page_number;
  const doi = category === 'upgrade'
    ? doiLink(check.matched?.doi) || doiLink(check.entry?.doi)
    : doiLink(check.entry?.doi) || doiLink(check.matched?.doi);
  const query = (check.entry?.title || check.matched?.title || original.replace(/^\s*\[\d+\]\s*/, '')).replace(/\s+/g, ' ').trim();
  const scholar = new URL('https://scholar.google.com/scholar');
  const baidu = new URL('https://xueshu.baidu.com/s');
  scholar.searchParams.set('q', query); baidu.searchParams.set('wd', query);
  return (
    <div className="reference-verification-details" data-reference-category={category}>
      <div className="reference-verification-heading">
        <span className={`reference-verification-category reference-category-${category}`}>{tags[category]}</span>
        <span className="reference-verification-reason">{reason}</span>
      </div>
      <div className="reference-verification-original">
        <h4>{original || text.noText}</h4>
      </div>
      {category !== 'verified' ? <p className="reference-verification-advice">{text.advice[category]}</p> : null}
      {comparisons.length ? (
        <details className="reference-verification-comparison" open>
          <summary>
            <ChevronRight size={14} aria-hidden="true" />
            {text.fields(comparisons.length)}
          </summary>
          <table>
            <thead><tr><th scope="col"><span className="sr-only">{text.fieldLabel}</span></th><th scope="col">{text.cited}</th><th scope="col">{text.matched}</th></tr></thead>
            <tbody>
            {comparisons.map((comparison, index) => (
              <tr key={`${comparison.field}-${index}`}>
                <th scope="row">{text.field[comparison.field as keyof typeof text.field] || comparison.field}</th>
                <td>{valueText(comparison.cited)}</td>
                <td className={`reference-cell-${comparison.status}`} title={text.status[comparison.status as keyof typeof text.status] || text.status.unknown}>
                  <span>{valueText(comparison.matched)}</span>
                  <small className={comparison.status === 'match' && valueText(comparison.cited) === valueText(comparison.matched) ? 'sr-only' : 'reference-field-status'}>
                    {text.status[comparison.status as keyof typeof text.status] || text.status.unknown}
                  </small>
                </td>
              </tr>
            ))}
            </tbody>
          </table>
        </details>
      ) : null}
      {(doi || query) ? <nav className="reference-verification-links" aria-label={text.relatedLinks}>
        {doi ? <a href={doi} target="_blank" rel="noopener noreferrer" onClick={event => event.stopPropagation()}>{text.openDoi}<ArrowUpRight size={13} aria-hidden="true" /></a> : null}
        {query ? <>
          <a href={scholar.toString()} target="_blank" rel="noopener noreferrer" onClick={event => event.stopPropagation()}>Google Scholar<ArrowUpRight size={13} aria-hidden="true" /></a>
          <a href={baidu.toString()} target="_blank" rel="noopener noreferrer" onClick={event => event.stopPropagation()}>{text.baiduScholar}<ArrowUpRight size={13} aria-hidden="true" /></a>
        </> : null}
      </nav> : null}
      {onNavigate && typeof page === 'number' && Number.isInteger(page) && page >= 1 ? (
        <button type="button" className="reference-verification-jump" onClick={onNavigate}>
          <MapPin size={13} aria-hidden="true" />
          {text.jumpToPage(page)}
        </button>
      ) : null}
    </div>
  );
}

export function referenceVerificationSummary(value: unknown): ReferenceVerificationSummary | null {
  if (!value || typeof value !== 'object' || !('entries' in value) || !Array.isArray(value.entries)) return null;
  const summary = value as ReferenceVerificationSummary;
  return {
    ...summary,
    entries: summary.entries.filter(
      (row) => row && categories.includes(row.category) && row.entry && typeof row.entry === 'object',
    ),
  };
}

export function ReferenceVerificationOverview({ summary, onSelectEntry }: {
  summary: ReferenceVerificationSummary;
  onSelectEntry?: (check: ReferenceVerificationEntry, index: number) => void;
}) {
  const { text, tags } = useCopy();
  const id = useId();
  // An extraction-failure diagnostic is not a processed bibliography entry.
  const entries = summary.entries.filter((entry) => entry.reason_code !== 'bibliography_not_extracted');
  const counts = Object.fromEntries(
    categories.map((category) => [category, entries.filter((entry) => entry.category === category).length]),
  );
  const verified = summary.entries.map((check, index) => ({ check, index })).filter(({ check }) => check.category === 'verified');
  return (
    <section className="reference-verification-overview" aria-labelledby={`${id}-title`}>
      <div className="reference-verification-overview-title">
        <CheckCircle2 size={16} aria-hidden="true" />
        <h3 id={`${id}-title`}>{text.summary}</h3>
        <span>{text.processed(entries.length)}</span>
      </div>
      <dl className="reference-verification-counts">
        {categories.map((category) => (
          <div key={category}>
            <dt>{tags[category]}</dt>
            <dd>{counts[category]}</dd>
          </div>
        ))}
      </dl>
      {summary.native_only ? <p className="reference-verification-native">{text.native}</p> : null}
      {verified.length ? (
        <details className="reference-verification-verified">
          <summary>
            <ChevronRight size={14} aria-hidden="true" />
            {text.verifiedEntries(verified.length)}
          </summary>
          <div>
            {verified.map(({ check, index }) => (
              <ReferenceVerificationDetails key={`${check.entry.id || 'reference'}-${index}`} check={check}
                onNavigate={onSelectEntry ? () => onSelectEntry(check, index) : undefined} />
            ))}
          </div>
        </details>
      ) : null}
    </section>
  );
}
