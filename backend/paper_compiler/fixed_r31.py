"""Fixed GB/T 7714-2025 checks over Paper IR and grounded source facts.

This is a manually authored detector, not a synthesized or repaired candidate.
Resource classification is a fixed source-extraction contract, not a verdict.
"""
from copy import deepcopy
from .programs import build_program

RULE_TEXT = "按GB/T 7714—2025检查正文引用标记和文末著录，保留条件义务及自动编号例外。"
DEFAULT_BASIS = [
    {"id":"gbt7714-2025:general","text":"题名和文献类型标识必备；电子资源载体条件必备。作者及多数出版字段有则必备；DOI、末尾句点不普遍必填。"},
    {"id":"gbt7714-2025:A","text":"类型M J N C D R S P EB A CM DS PP G CP DB Z；载体MT DK CD OL MM。类型及载体置于方括号内，载体前用/。"},
    {"id":"gbt7714-2025:8.11","text":"一般网站网页的题名、类型、载体、引用日期和获取路径必备；以网页形式出现的其他文献按其实际类型处理。"},
    {"id":"gbt7714-2025:9.1-9.2","text":"顺序编码引用用方括号，多个编号用逗号、连续编号用短横线；自动编号有例外，缺少生成信息不得否定例外。"}
]
CONTEXT_NAME = "r31_source_context"
CONTEXT_INSTRUCTIONS = """Extract resource_kind and electronic_medium from the supplied actual source context, not a compliance verdict.
resource_kind is one of book, book_chapter, journal_article, newspaper_article, conference, thesis, report, standard, patent, webpage, archive, map, dataset, preprint, collection, computer_program, database, other. Return UNKNOWN if the actual resource cannot be established.
Do NOT infer actual kind from the [J]/[M]/[C] marker being checked, from a familiar title, or from the paper's topic. Quote the actual publication/container facts establishing the classification. Distinguish conference genre from book publication form: proceedings may also be published as books or book chapters. Report the source-supported publication class, but do not infer that book form alone requires a different bibliography type marker; GB/T 7714-2025 8.6.1 permits C for conference proceedings using book-format publication items. Do not treat a conference mentioned only in a work's topic as conference publication evidence. A Journal container and serial publication facts may support journal_article; a missing or ambiguous venue cannot.
electronic_medium is observed true only with independent source evidence that the cited resource itself is electronic. A URL/DOI/link or the marker /OL alone does not establish this; URLs may accompany print works. A general website/webpage is electronic. Return unknown rather than guessing.
An entry title's spelling, automatic PDF line wraps, line-end hyphens, layout whitespace or absent external metadata do not establish a format defect. Do not repair text. Both observed attributes require exact source quotes and source IDs. No previous detector output or labels are available."""

CODE = r"""def detect(payload):
    output = []
    basis = BASIS_IDS
    types = ['M','J','N','C','D','R','S','P','EB','A','CM','DS','PP','G','CP','DB','Z']
    carriers = ['MT','DK','CD','OL','MM']
    expected = {'book':'M','book_chapter':'M','journal_article':'J','newspaper_article':'N','conference':'C','thesis':'D','report':'R','standard':'S','patent':'P','webpage':'EB','archive':'A','map':'CM','dataset':'DS','preprint':'PP','collection':'G','computer_program':'CP','database':'DB','other':'Z'}
    analysis = payload.get('analysis', {})
    for node in nodes(payload, 'BibliographyEntry'):
        text = node.get('text') or ''
        complete = analysis.get('coverage', {}).get(node['id'], {}).get('status') == 'complete'
        fields = analysis.get('results', {}).get('bibliography_fields', {}).get(node['id'], {})
        failures = []
        gaps = []
        evidence = [node['id']]
        title = fields.get('title', {})
        if title.get('state') == 'confirmed_absent' and complete:
            failures.append('缺少必备题名')
        elif title.get('state') != 'observed':
            gaps.append('题名抽取不足')
        # Overlapping extracted roles cannot establish a publication year.
        year = fields.get('year', {})
        title_range = title.get('source_range')
        year_range = year.get('source_range')
        if title.get('state') == 'observed' and year.get('state') == 'observed' and isinstance(title_range, list) and isinstance(year_range, list) and len(title_range) == 2 and len(year_range) == 2:
            if all(isinstance(v, int) for v in title_range + year_range) and 0 <= title_range[0] <= year_range[0] < year_range[1] <= title_range[1] <= len(text):
                if year_range[1] - year_range[0] == 4 and text[year_range[0]:year_range[1]] == str(year.get('value')):
                    gaps.append('题名与出版年份的来源范围重叠，字段角色未确立')
        tail = text
        value = title.get('value')
        if title.get('state') == 'observed' and isinstance(value, str) and value in text:
            tail = text[text.find(value) + len(value):]
        markers = re_findall(r'[\[［]\s*([A-Za-z]{1,3}(?:\s*/\s*[A-Za-z]{1,3})*)\s*[\]］]', tail)
        marker = markers[0].replace(' ', '').replace('\n', '').replace('\r', '').replace('\t', '') if markers else ''
        pieces = marker.split('/') if marker else []
        code = pieces[0] if pieces else ''
        carrier = pieces[1] if len(pieces) == 2 else ''
        if not marker:
            field = fields.get('type_code', {})
            if complete and field.get('state') in ['confirmed_absent','observed']:
                failures.append('缺少方括号内的文献类型标识')
            else:
                gaps.append('类型标识抽取不足')
        else:
            if code not in types:
                failures.append('文献类型代码不在规范附录A内')
            if len(pieces) > 2 or (len(pieces) == 2 and carrier not in carriers):
                failures.append('载体代码错误或重复')
            if re_search(r'[\]］]\s*[.。]?\s*[\[［]\s*(?:M|J|N|C|D|R|S|P|EB|A|CM|DS|PP|G|CP|DB|Z|MT|DK|CD|OL|MM)\s*[\]］]', tail):
                failures.append('类型或载体标识重复或被拆为独立方括号')
        context = fact(payload, 'r31_source_context', node['id'], 'resource_kind')
        kind = context.get('value') if context.get('state') == 'observed' and context.get('evidence_ids') else None
        conference_book_form = False
        if kind in expected:
            evidence.extend(context['evidence_ids'])
            if kind in ['book','book_chapter'] and code == 'C':
                publication = fields.get('container', {})
                publication_range = publication.get('source_range')
                publication_value = publication.get('value')
                if publication.get('state') == 'observed' and publication.get('evidence_ids') and isinstance(publication_value, str) and isinstance(publication_range, list) and len(publication_range) == 2:
                    if all(isinstance(v, int) for v in publication_range) and 0 <= publication_range[0] < publication_range[1] <= len(text):
                        publication_source = text[publication_range[0]:publication_range[1]]
                        if ''.join(publication_source.split()) == ''.join(publication_value.split()) and re_search(r'(?i)\bproceedings\s+of\b|\b(?:international|annual)\s+(?:conference|colloquium|symposium|workshop)\b|会议录|会议论文集|研讨会论文集', publication_source):
                            conference_book_form = True
                            evidence.extend(publication['evidence_ids'])
            if code in types and code != expected[kind] and not conference_book_form:
                if kind == 'conference' and code == 'M':
                    gaps.append('会议文献按图书形式著录的规范例外尚未排除')
                else:
                    failures.append('类型标识与独立来源证实的资源种类不一致')
        else:
            gaps.append('实际资源种类未确立')
        electronic = fact(payload, 'r31_source_context', node['id'], 'electronic_medium')
        medium_known = electronic.get('state') == 'observed' and bool(electronic.get('evidence_ids'))
        is_electronic = medium_known and electronic.get('value') is True
        if medium_known:
            evidence.extend(electronic['evidence_ids'])
        required = []
        # /OL is an explicit declaration of online access in this entry.
        # Its access-path obligation does not need a second medium guess.
        if carrier == 'OL':
            required.append('url')
        if is_electronic or kind == 'webpage':
            if marker and not carrier:
                failures.append('已证实电子资源缺少载体标识')
            required.append('url')
        if kind == 'webpage':
            required.append('access_date')
        if kind in ['dataset','preprint']:
            required.append('access_date')
        if kind == 'preprint':
            required.append('url')
        if kind == 'thesis':
            required.append('institution')
        if kind == 'standard':
            required.append('standard_number')
        if kind == 'patent':
            required.extend(['authors','patent_number'])
        # Conditional omission is established only by existing work evidence.
        page_field = fields.get('pages', {})
        page_scope = kind == 'journal_article' or ((kind == 'conference' or conference_book_form) and re_search(r'[\[［]C(?:/[A-Z]{2})?[\]］]\s*//', tail))
        if complete and page_scope and page_field.get('state') == 'confirmed_absent':
            identity = fact(payload, 'external_work', node['id'], 'exists')
            available = fact(payload, 'external_work', node['id'], 'available_fields')
            if identity.get('state') == 'observed' and identity.get('value') is True and identity.get('evidence_ids'):
                if available.get('state') == 'observed' and isinstance(available.get('value'), list) and 'pages' in available['value'] and available.get('evidence_ids'):
                    failures.append('同一作品的独立元数据已证实存在页码，但完整条目未著录')
                    evidence.extend(identity['evidence_ids'])
                    evidence.extend(available['evidence_ids'])
        compact_source = ''.join(text.split())
        access_present = fields.get('url', {}).get('state') == 'observed' or fields.get('doi', {}).get('state') == 'observed' or re_search(r'(?i)(?:[a-z][a-z0-9+.-]*://|www\.|doi:|10\.[0-9]{4,9}/)', compact_source)
        for name in required:
            field = fields.get(name, {})
            if name == 'url':
                if access_present:
                    continue
                if complete:
                    failures.append('完整联机或电子资源条目缺少访问路径或永久标识符')
                else:
                    gaps.append('访问路径抽取或条目边界不完整')
                continue
            if field.get('state') == 'confirmed_absent' and complete:
                failures.append('适用资源类型缺少必备字段：' + name)
            elif field.get('state') != 'observed':
                gaps.append('适用必备字段未知：' + name)
        for name in ['access_date']:
            field = fields.get(name, {})
            if field.get('state') == 'observed' and not re_matches(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', field.get('value', '')):
                failures.append('已著录日期不符合YYYY-MM-DD：' + name)
        # Use the grounded container boundary, not the extractor's first year.
        container = fields.get('container', {})
        if kind == 'conference' and container.get('state') != 'observed':
            container = fields.get('conference', {})
        container_range = container.get('source_range')
        container_value = container.get('value')
        if container.get('state') == 'observed' and isinstance(container_value, str) and container_value.strip() and isinstance(container_range, list) and len(container_range) == 2:
            if all(isinstance(v, int) for v in container_range) and 0 <= container_range[0] < container_range[1] <= len(text):
                container_source = text[container_range[0]:container_range[1]]
                if ''.join(container_source.split()) == ''.join(container_value.split()):
                    if complete and title.get('state') == 'observed' and isinstance(value, str) and value.strip() and isinstance(title_range, list) and len(title_range) == 2:
                        if all(isinstance(v, int) for v in title_range) and 0 <= title_range[0] < title_range[1] <= container_range[0]:
                            if ''.join(text[title_range[0]:title_range[1]].split()) == ''.join(value.split()):
                                type_position = text[title_range[1]:container_range[0]]
                                if re_matches(r'\s*(?:[.。]|//)?\s*', type_position):
                                    failures.append('已核验题名与出版容器之间缺少必备类型标识')
                    before_container = text[:container_range[0]]
                    after_container = text[container_range[1]:]
                    if kind == 'journal_article' and code == 'J':
                        front_year = re_findall(r'[\[［]J(?:\s*/\s*[A-Z]{2})?[\]］]\s*[.。]\s*((?:18|19|20|21)[0-9]{2})\s*[.。]\s*$', before_container)
                        journal_year = re_findall(r'^\s*[,，]\s*((?:18|19|20|21)[0-9]{2})\s*[,，:：]', after_container)
                        if front_year and journal_year and front_year[0] == journal_year[0]:
                            failures.append('期刊类型标识与刊名之间重复插入出版年')
                    if kind == 'journal_article' and code == 'J':
                        repeated_year_sequences = re_findall(r'^\s*[,，]\s*((?:18|19|20|21)[0-9]{2})((?:\s*[,，]\s*(?:18|19|20|21)[0-9]{2})+)\s*[,，]\s*[0-9]+(?:\s*[(（][0-9]+[)）])?\s*[:：]\s*[0-9]+(?:\s*[-–]\s*[0-9]+)?\s*[.。]', after_container)
                        for sequence in repeated_year_sequences:
                            extra_years = re_findall(r'(?:18|19|20|21)[0-9]{2}', sequence[1])
                            if extra_years and all(extra == sequence[0] for extra in extra_years):
                                failures.append('期刊容器与独立卷期页段之间相邻重复出版年')
                    if kind == 'conference' and code == 'C':
                        adjacent_years = re_findall(r'^\s*[.。]\s*((?:18|19|20|21)[0-9]{2})\s*[,，.。]\s*((?:18|19|20|21)[0-9]{2})\s*[:：]\s*[0-9]+(?:\s*[-–]\s*[0-9]+)?\s*(?:[.。]|$)', after_container)
                        if adjacent_years and adjacent_years[0][0] == adjacent_years[0][1]:
                            failures.append('会议容器后的出版段相邻重复同一出版年')
        # A terminal duplicate in the declared conference publication segment
        # does not depend on which occurrence the year extractor selected.
        if complete and code == 'C' and not access_present:
            terminal_years = re_findall(r'[\[［]\s*C\s*[\]］]\s*//[\s\S]*[.。]\s+((?:18|19|20|21)[0-9]{2})\s*[.。]\s+((?:18|19|20|21)[0-9]{2})[.。]?\s*$', tail)
            if terminal_years and terminal_years[0][0] == terminal_years[0][1]:
                failures.append('会议出版段末尾相邻重复同一出版年')
        if complete and code == 'C':
            orphan_types = re_findall(r'[\[［]C(?:/[A-Z]{2})?[\]］]\s*//[^［］\[\]]+?[.。]\s*(?:18|19|20|21)[0-9]{2}\s*[:：]\s*[0-9]+(?:\s*[-–]\s*[0-9]+)?[.。]\s*[\[［]([A-Z]{1,3})[\]］][.。]?\s*$', tail)
            if any(orphan in types and orphan != code for orphan in orphan_types):
                failures.append('完整会议出处及年页段之后尾附无内容的异类文献标识')
        # Compare complete literal publication blocks, not URL/year overlap alone.
        compact_tail = ''.join(tail.split())
        if complete and len(markers) == 1 and code == 'C' and carrier == 'OL':
            url_fact = fields.get('url', {})
            if url_fact.get('state') == 'observed' and isinstance(url_fact.get('value'), str) and url_fact.get('evidence_ids'):
                publication_url = ''.join(url_fact['value'].split()).rstrip('.。')
                if publication_url and compact_tail.count(publication_url) == 2:
                    url_parts = compact_tail.split(publication_url)
                    repeated_block = url_parts[1].lstrip('.。')
                    if not url_parts[2].strip('.。') and len(repeated_block) >= 40 and url_parts[0].endswith(repeated_block):
                        if re_matches(r'(?:18|19|20|21)[0-9]{2}[,，].+[.。].*[,，](?:18|19|20|21)[0-9]{2}[.。]', repeated_block):
                            failures.append('同一会议条目中出版年地点出版者及相同访问路径整块重复')
                            evidence.extend(url_fact['evidence_ids'])
        if complete and kind == 'journal_article' and code == 'J' and len(markers) == 1:
            serial_tuples = re_findall(r'(?:18|19|20|21)[0-9]{2},[0-9]+(?:\([0-9]+\))?:[0-9]+(?:[-–][0-9]+)?[.。]', compact_tail)
            for serial_tuple in set(serial_tuples):
                if compact_tail.count(serial_tuple) == 2:
                    serial_parts = compact_tail.split(serial_tuple)
                    repeated_container = serial_parts[1]
                    leading_year = re_findall(r'^((?:18|19|20|21)[0-9]{2}[.。])', repeated_container)
                    if leading_year:
                        repeated_container = repeated_container[len(leading_year[0]):]
                    if not serial_parts[2].strip('.。') and len(repeated_container) >= 32 and serial_parts[0].endswith(repeated_container):
                        if re_search(r'[A-Za-z一-龥]', repeated_container) and not re_search(r'[\[［\]］]', repeated_container):
                            failures.append('同一类型标识后长字面容器后缀及完整年卷期页段重复')
        end_year = re_findall(r'[.。]\s+((?:18|19|20|21)[0-9]{2})[.。]?\s*$', tail)
        publication_years = re_findall(r'((?:18|19|20|21)[0-9]{2})\s*[,，:：]\s*[0-9][0-9\s,，()（）:：\-–]*[.。]', tail)
        if complete and kind == 'journal_article' and code == 'J':
            before_doi_years = re_findall(r'(?i)[.。]\s+((?:18|19|20|21)[0-9]{2})[.。]\s+(?:doi\s*:|https?://(?:dx\.)?doi\.org/)', tail)
            if any(year_value in publication_years for year_value in before_doi_years):
                failures.append('完整年卷页之后、DOI之前重复追加同一出版年')
        if complete:
            publication_segments = re_findall(r'([\[［][A-Z]{1,3}(?:/[A-Z]{2})?[\]］]\s*//[^［］\[\]]+?[.。]\s*(?:18|19|20|21)[0-9]{2}\s*[:：]\s*[0-9]+(?:\s*[-–]\s*[0-9]+)?[.。])', tail)
            normalized_segments = [''.join(segment.split()) for segment in publication_segments]
            if len(normalized_segments) > len(set(normalized_segments)):
                failures.append('同一条目内完整类型标识、出处、出版年及页码段完全重复')
        if end_year and end_year[-1] in publication_years:
            failures.append('完整年卷页著录之后又重复追加同一出版年')
        if not complete:
            gaps.append('条目边界或抽取覆盖不完整')
        status = 'VIOLATION' if failures else 'UNKNOWN' if gaps else 'PASS'
        message = '；'.join(failures) if failures else '；'.join(gaps) if gaps else '已核查的适用著录义务满足，未强制可选字段。'
        output.append(emit(node, status, message, check_id='bibliographic_format', basis=basis, evidence_ids=list(set(evidence)), reasons=gaps))
    group_status = {}
    for node in nodes(payload, 'CitationGroup'):
        text = (node.get('text') or '').strip()
        automatic = fact(payload, 'citation_syntax', node['id'], 'automatic_footnote')
        manual = automatic.get('state') == 'observed' and automatic.get('value') is False
        if re_matches(r'[\[［]\s*[0-9]+(?:\s*(?:,|，|-|–)\s*[0-9]+)*\s*[\]］]', text):
            status = 'PASS'
            reason = '采用允许的数字引用标记；不否定自动编号例外。'
        elif re_matches(r'.*[(（][^()（）]*[12][0-9]{3}[a-z]?[^()（）]*[)）].*', text):
            status = 'PASS'
            reason = '采用允许的著者-出版年或叙述式引用形式。'
        elif manual:
            status = 'VIOLATION'
            reason = '已证实非自动编号的引用标记不符合括号和分隔形式。'
        else:
            status = 'UNKNOWN'
            reason = '标记适用体例或自动编号状态未确立。'
        group_status[node['id']] = status
        output.append(emit(node, status, reason, check_id='citation_marker', basis=basis, reasons=[reason] if status == 'UNKNOWN' else []))
    groups = {n['id']: n for n in nodes(payload, 'CitationGroup')}
    for node in nodes(payload, 'Paragraph'):
        selected = [group_status[g] for g in groups if g in node.get('children', [])]
        status = 'VIOLATION' if 'VIOLATION' in selected else 'PASS' if selected and all(s == 'PASS' for s in selected) else 'UNKNOWN'
        message = '正文引用标记已按适用体例检查。' if status == 'PASS' else '正文标记或适用体例尚未全部确立。'
        if status == 'VIOLATION':
            message = '正文含已证实不符合适用体例的引用标记。'
        output.append(emit(node, status, message, check_id='paragraph_citations', basis=basis, reasons=[message] if status == 'UNKNOWN' else []))
    for node in nodes(payload, 'ReferenceUse'):
        system = fact(payload, 'citation_order', node['id'], 'system')
        value = fact(payload, 'citation_order', node['id'], 'numeric_value')
        rank = fact(payload, 'citation_order', node['id'], 'first_appearance_rank')
        first = fact(payload, 'citation_order', node['id'], 'is_first_use')
        parent = None
        for group in groups.values():
            if node['id'] in group.get('children', []):
                parent = group
        automatic = fact(payload, 'citation_syntax', parent['id'], 'automatic_footnote') if parent else {}
        manual = automatic.get('state') == 'observed' and automatic.get('value') is False
        status = 'UNKNOWN'
        message = '首次引用顺序或自动脚注例外未有完整证据。'
        if system.get('state') == 'observed' and system.get('value') == 'numeric' and value.get('state') == 'observed' and rank.get('state') == 'observed' and first.get('state') == 'observed':
            if first.get('value') is False or value.get('value') == rank.get('value'):
                status = 'PASS'
                message = '已核验引用序号的首次次序或重复引用。'
            elif manual:
                status = 'VIOLATION'
                message = '完整正文证据中首次引用序号不连续且已排除自动脚注例外。'
        output.append(emit(node, status, message, check_id='citation_order', basis=basis, reasons=[message] if status == 'UNKNOWN' else []))
    return output
"""


def build_r31_package(*, model=None, basis=None, rule_text=None):
    basis = deepcopy(DEFAULT_BASIS if basis is None else basis)
    if not isinstance(basis, list) or not basis or any(
        not isinstance(b, dict) or not isinstance(b.get("id"), str) or not b["id"] or
        not isinstance(b.get("text"), str) or not b["text"].strip() for b in basis):
        raise ValueError("R31 requires normative basis")
    if len({b["id"] for b in basis}) != len(basis):
        raise ValueError("duplicate R31 basis IDs")
    request = {"name":CONTEXT_NAME,"targets":["BibliographyEntry"],
               "fields":{"resource_kind":"string","electronic_medium":"boolean"},
               "instructions":CONTEXT_INSTRUCTIONS}
    return build_program({"rule_id":"31","title":"引用与著录格式",
        "requires":["bibliography_fields","bibliography_shape","citation_syntax","citation_order","external_work",CONTEXT_NAME],
        "target_kinds":["BibliographyEntry","Paragraph","CitationGroup","ReferenceUse"],
        "code":CODE.replace("BASIS_IDS",repr([b["id"] for b in basis])),
        "analysis_requests":[request],"model_patch":{}},
        rule_text=RULE_TEXT if rule_text is None else rule_text,basis=basis,model=model)


build_package = build_r31_package
