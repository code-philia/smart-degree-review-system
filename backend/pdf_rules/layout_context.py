"""Page roles and original-PDF evidence shared by text and caption rules."""
from collections import defaultdict
from dataclasses import replace
import re

from .mineru_layout import LayoutObject, _caption_kind
from .model import PdfDocument, PdfLine
from .native_layout import in_margin, text_covers_region, _union_area
from .native_diagrams import reclassify_flow_diagrams
from .caption_context import contextual_caption, paragraph_start
from .numbering import normalize_text, is_toc_line, FIGURE_CAPTION, TABLE_CAPTION, FIGURE_REFERENCE, TABLE_REFERENCE, APPENDIX_REFERENCE, normalize_label, toc_line_keys

ADMIN_TITLE = re.compile(r"(?:[\u4e00-\u9fffA-Za-z]{2,30}大学)?(?:硕士|博士)?(?:学位论文(?:原创性声明|使用授权|授权使用|答辩决议(?:书)?|授权使用声明|版权使用授权(?:书)?)|答辩(?:决议书|委员会决议)|原创性声明|版权使用授权(?:书)?|declaration\s*of\s*originality)", re.I)
COVER_TITLE = re.compile(r"(?:硕士|博士)学位论文|(?:master.?s|doctoral|ph.?d.?)\s+(?:thesis|dissertation)", re.I)
CHAPTER = re.compile(r"^第\s*[一二三四五六七八九十0-9]+\s*章|^chapter\s+[0-9IVX]+", re.I)
PANEL = re.compile(r"[（(]{0,2}([a-z])[）)]{1,2}", re.I)


def _panel_match(text):
    normalized=normalize_text(text).strip()
    match=PANEL.search(normalized)
    # MuPDF can merge an axis tick with the panel heading on the same row.
    return match if match and (match.start()==0 or re.fullmatch(r'[0-9.\s+\-eE×^]+',normalized[:match.start()])) else None


def _complete_decision_schema(text):
    """A complete candidate form and its formal verdict, not isolated words."""
    value=normalize_text(text).replace(" ", "")
    fields=("姓名","学号","所在学科","指导教师","答辩日期","答辩地点","论文题目")
    return (all(word in value for word in fields) and "评语和决议" in value
            and "答辩委员会" in value and "无记名投票" in value
            and bool(re.search(r"同意通过.{0,80}学位论文答辩",value))
            and bool(re.search(r"建议授予.{0,80}学位",value)))


def decision_form(page):
    if any(CHAPTER.match(normalize_text(line.text)) for line in page.lines):
        return False
    if any(_caption_kind(line.text) for line in page.lines):
        return False
    fields = [line for line in page.lines if line.role in {"table", "table_body"}]
    text = "".join(normalize_text(line.text).replace(" ", "") for line in fields)
    outside_reference=any(line.role not in {"table","table_body"}
                          and any(pattern.search(normalize_text(line.text)) for pattern in
                                  (FIGURE_REFERENCE,TABLE_REFERENCE,APPENDIX_REFERENCE))
                          for line in page.lines)
    if _complete_decision_schema(text) and not outside_reference:
        return True
    if all(marker in text for marker in ("论文评审", "选题与综述", "总体评价",
                                         "答辩委员会成员", "姓名", "工作单位",
                                         "答辩审批意见", "指导教师意见", "学位评定分委员会意见")):
        return True
    # A sideways complete decision form may lose its title and handwritten
    # conclusion in OCR. Require both the detailed candidate schema and the
    # multi-member committee/signature schema; standalone research references
    # outside those table regions prevent administrative exclusion.
    candidate_fields=("姓名","学号","所在学科","指导教师","答辩日期","答辩地点","论文题目")
    committee_fields=("答辩委员会","工作职务","职称","工作单位","签名","主席","秘书")
    references=(FIGURE_REFERENCE,TABLE_REFERENCE,APPENDIX_REFERENCE)
    if (all(marker in text for marker in candidate_fields+committee_fields)
            and text.count("委员")>=3
            and not any(line.role not in {"table","table_body"}
                        and any(pattern.search(normalize_text(line.text)) for pattern in references)
                        for line in page.lines)):
        return True
    return ("答辩日期" in text and "论文题目" in text
            and any(marker in text for marker in ("答辩结论", "投票表决结果"))
            and any(marker in text for marker in ("答辩委员会", "工作职务"))
            and "姓名" in text)


def nonresearch_pages(document):
    excluded = {page.number for page in document.pages if nonresearch_page(page)}
    for previous, page in zip(document.pages, document.pages[1:]):
        text = "".join(normalize_text(line.text).replace(" ", "") for line in page.lines)
        if (page.number == previous.number + 1 and decision_form(previous)
                and (("主席" in text and "秘书" in text and text.count("委员") >= 3)
                     or (len(text) < 300 and "秘书" in text
                         and (any(word in text for word in ("学院", "职称", "工作单位"))
                              or any(re.fullmatch(r"秘书[\u4e00-\u9fff]{2,12}", normalize_text(line.text).replace(" ", "")) for line in page.lines))
                         and all(line.bbox[3] < page.height * 0.3 for line in page.lines)))
                and page.ink_bottom is not None
                and page.ink_bottom <= max((line.bbox[3] for line in page.lines), default=0) + 20
                and all(line.bbox[3] < page.height * .5 for line in page.lines)
                and len(text) < 1500 and not any(CHAPTER.match(normalize_text(line.text)) for line in page.lines)):
            excluded.add(page.number)
    return excluded


def nonresearch_page(page):
    if any(CHAPTER.match(normalize_text(line.text)) for line in page.lines):
        return False
    text = "".join(normalize_text(line.text).replace(" ", "") for line in page.lines)
    # Physically sideways scans can put a declaration title outside the top band.
    # Require both a standalone title and the legal declaration itself.
    statement = page.width > page.height and any(
        ADMIN_TITLE.fullmatch(normalize_text(line.text).replace(" ", ""))
        and (line.source == "native" or line.role == "title")
        and line.bbox[3] - line.bbox[1] >= 2 * (line.bbox[2] - line.bbox[0])
        for line in page.lines)
    vertical_letters = sum(len(line.text) for line in page.lines
                           if line.bbox[3] - line.bbox[1] >= 2 * (line.bbox[2] - line.bbox[0]))
    sideways = vertical_letters >= sum(len(line.text) for line in page.lines) * .8
    research_reference = any(pattern.search(text) for pattern in
                             (FIGURE_REFERENCE, TABLE_REFERENCE, APPENDIX_REFERENCE))
    legal = (("本人郑重声明" in text and "学位论文" in text
              and "本声明的法律" in text)
             or ("本学位论文作者" in text and "学校" in text
                 and "保留" in text and "查阅" in text and "借阅" in text))
    if statement and sideways and legal and not research_reference and not any(_caption_kind(line.text) for line in page.lines):
        return True
    def viewer_top(line, lower=0, upper=.3):
        angle=page.display_rotation%360
        y=({0:line.bbox[1],90:line.bbox[0],180:page.height-line.bbox[3],270:page.width-line.bbox[2]})[angle]
        height=page.width if angle in {90,270} else page.height
        return lower <= y / height < upper
    top_lines = [normalize_text(line.text).replace(" ", "") for line in page.lines
                 if viewer_top(line) and len(line.text) < 100]
    administrative_title=any(ADMIN_TITLE.fullmatch(text) for text in top_lines)
    if research_reference or any(_caption_kind(line.text) for line in page.lines):
        administrative_title=False
    if decision_form(page) or administrative_title:
        return True
    text = "".join(normalize_text(line.text).replace(" ", "") for line in page.lines)
    # A logo can place the standalone degree heading well below the top band.
    # A running university header is not evidence that this page is a cover.
    cover_titles = [normalize_text(line.text).replace(" ", "") for line in page.lines
                    if viewer_top(line, .08, .7) and len(line.text) < 100]
    generic_cover = any(re.fullmatch(r"[\u4e00-\u9fffA-Za-z]{2,30}大学(?:专业(?:学位)?)?(?:硕士|博士)?学位论文", title)
                        for title in cover_titles)
    identity_fields = sum(word in text for word in ("姓名", "学号", "导师", "学院", "专业"))
    cover = any(COVER_TITLE.search(title) for title in top_lines) or (generic_cover and identity_fields >= 3)
    return (not research_reference and not any(_caption_kind(line.text) for line in page.lines)
            and len(text) < 1500 and cover
            and any(word in text for word in ("作者", "导师", "专业", "Author", "Supervisor"))
            and not any(CHAPTER.match(normalize_text(line.text)) for line in page.lines))


def recover_document(document, objects):
    """OCR sparse/raster pages without treating a few words as complete body text."""
    by_page = defaultdict(list)
    for obj in objects:
        by_page[obj.page_number].append(obj)
    pages = []
    for page in document.pages:
        parsed = by_page[page.number]
        if not page.unreadable:
            # Some PDF headings are painted as vector outlines while their
            # paragraphs remain native text. Recover the independently parsed
            # administrative heading so the whole form can be classified.
            headings = [obj for obj in parsed if obj.kind == 'text'
                        and ADMIN_TITLE.fullmatch(normalize_text(obj.text).replace(' ', ''))]
            # Outlined fonts can leave a nominally readable page with no native
            # form text. Project only complete, bounded administrative schemas;
            # the later region classifier still checks the preceding form and
            # preserves every figure/reference outside the actual signature grid.
            administrative_tables=[]
            for obj in parsed:
                if obj.kind!='text' or obj.role not in {'table','table_body'}:
                    continue
                value=normalize_text(obj.text).replace(' ', '')
                roster_fields=("答辩委员会","工作职务","姓名","职称","工作单位","签名","主席","秘书")
                roster=(all(word in value for word in roster_fields)
                        and value.count("委员")>=3 and obj.bbox[3]<page.height*.5)
                if _complete_decision_schema(value) or roster:
                    administrative_tables.append(obj)
            if headings or administrative_tables:
                lines=list(page.lines)
                for obj in headings+administrative_tables:
                    if any(normalize_text(line.text).replace(' ', '')==
                           normalize_text(obj.text).replace(' ', '')
                           and containment(obj.bbox,line.bbox)>=.8 for line in lines):
                        continue
                    lines.append(PdfLine(page.number,obj.text,obj.bbox,page.width,page.height,
                                         source='mineru',role=obj.role))
                page=replace(page,lines=tuple(sorted(lines,key=lambda line:(line.bbox[1],line.bbox[0]))))
        if page.unreadable:
            text_objects = [obj for obj in parsed if obj.text and obj.kind in
                            {"text", "figure_caption", "table_caption"}]
            # Preserve existing native headings and captions during OCR recovery.
            lines = [line for line in page.lines if line.source == "native"]
            for obj in sorted(text_objects, key=lambda obj: (obj.bbox[1], obj.bbox[0])):
                if not any(normalize_text(line.text) == normalize_text(obj.text)
                           and containment(obj.bbox, line.bbox) > 0.8 for line in lines):
                    lines.append(PdfLine(page.number, obj.text, obj.bbox, page.width, page.height, source="mineru", role=obj.role))
            candidate = replace(page, lines=tuple(sorted(lines, key=lambda line: (line.bbox[1], line.bbox[0]))))
            body = []
            for obj in text_objects:
                if obj.kind != "text" or obj.role in {"title", "header", "footer", "discarded"}:
                    continue
                for text, box in obj.text_lines:
                    # Overlapping OCR crops describe the same ink, not extra body.
                    if not any(normalize_text(line.text).strip() == normalize_text(text).strip()
                               and (containment(box, line.bbox) > .8
                                    or containment(line.bbox, box) > .8) for line in body):
                        body.append(PdfLine(page.number, text, box, page.width, page.height))
            regions = [box for box in page.images if not in_margin(box, page.width, page.height, page.display_rotation)]
            resolved = bool(regions) and all(
                text_covers_region(body, box) for box in regions)
            resolved = resolved or captioned_native_graphic(page, parsed, regions)
            page = replace(candidate, unreadable=not (nonresearch_page(candidate) or resolved))
        pages.append(page)
    return PdfDocument(document.path, tuple(pages))


def research_document(document):
    excluded = nonresearch_pages(document)
    return PdfDocument(document.path, tuple(
        replace(page, lines=(), unreadable=False) if page.number in excluded else page
        for page in document.pages))


def _native_caption_carrier(page, objects, region):
    """A bounded raster copy whose complete caption is already native text."""
    height = region[3] - region[1]
    width = region[2] - region[0]
    if width <= 0 or height <= 0 or height > page.height * .18:
        return False
    lines = sorted((line for line in page.lines if line.source == 'native'
                    and region[0] <= (line.bbox[0] + line.bbox[2]) / 2 <= region[2]
                    and region[1] <= (line.bbox[1] + line.bbox[3]) / 2 <= region[3]),
                   key=lambda line: (line.bbox[1], line.bbox[0]))
    if not lines or _caption_kind(lines[0].text) != 'figure_caption':
        return False
    def horizontal_coverage(box):
        return max(0, min(region[2], box[2]) - max(region[0], box[0])) / width
    # Paragraph rows span their caption carrier; only its final row may end
    # early. Left-column native text does not establish unseen right-column
    # raster content, even when a parser gives the caption an overwide box.
    if any(horizontal_coverage(line.bbox) < .75 for line in (lines[:-1] or lines)):
        return False
    # Require independent cloud caption evidence at this native text, rather
    # than calling any narrow scanned paragraph a caption layer.
    # Mathematical caption tokens may be Unicode in native text and LaTeX in
    # cloud text. Match the leading caption identity and subject before them.
    prefix = re.sub(r'\s+', '', normalize_text(lines[0].text))[:12]
    if not any((obj.kind == 'figure_caption' or obj.role in {'image_caption', 'chart_caption'})
               and containment(lines[0].bbox, obj.bbox) >= .65
               and horizontal_coverage(obj.bbox) >= .85
               and re.sub(r'\s+', '', normalize_text(obj.text)).startswith(prefix)
               for obj in objects):
        return False
    letters = sum(len(re.findall(r'[A-Za-z\u4e00-\u9fff]', line.text)) for line in lines)
    top = min(line.bbox[1] for line in lines)
    bottom = max(line.bbox[3] for line in lines)
    cursor = region[1]
    gap = 0
    for line in lines:
        gap = max(gap, line.bbox[1] - cursor)
        cursor = max(cursor, line.bbox[3])
    gap = max(gap, region[3] - cursor)
    return (letters >= 40 and bottom - top >= height * .55
            and top <= region[1] + max(3, height * .2)
            and bottom >= region[3] - max(20, height * .25)
            and gap <= max(20, height * .35))


def captioned_native_graphic(page, objects, regions):
    """Native explanations and matching layout prove bounded research images.

    Every raster needs graphic coverage or a fully extracted caption copy.
    A layout image label alone never proves that scanned prose was extracted.
    """
    regions = [region for region in regions
               if not _native_caption_carrier(page, objects, region)]
    if not regions:
        return False
    box = union(regions)
    if (box[1] < page.height * 0.03 or box[3] > page.height * 0.97
            or box[2] - box[0] > page.width * 0.95
            or box[3] - box[1] > page.height * 0.92):
        return False
    def adjacent_caption(line, region):
        x1,y1,x2,y2=line.bbox
        vertical=abs(line.direction[1])>.8 and y2-y1>2*(x2-x1)
        if vertical:
            side_distance=min(abs(x1-region[2]),abs(region[0]-x2))
            overlap=max(0,min(y2,region[3])-max(y1,region[1]))
            return side_distance<=60 and overlap>=.5*min(y2-y1,region[3]-region[1])
        return (-2<=y1-region[3]<=60 and max(x1,region[0])<min(x2,region[2]))
    native = [line for line in page.lines if line.source == 'native']
    captions = [line for line in native if _caption_kind(line.text) == 'figure_caption']
    panels = []
    for line in sorted(native, key=lambda line: (line.bbox[1], line.bbox[0])):
        match = _panel_match(line.text)
        if (match and len(re.findall(r'[A-Za-z\u4e00-\u9fff]', line.text[match.end():])) >= 4
                and any(adjacent_caption(line, region) for region in regions)):
            panels.append((match.group(1).lower(), line))
    # Independent consecutive subpanel explanations can span a figure across
    # pages. They establish readability without inventing its missing title.
    letters = [ord(label) for label, _ in panels]
    if len(letters) >= 2 and all(right == left + 1 for left, right in zip(letters, letters[1:])):
        captions += [line for _, line in panels]
    if not captions:
        return False
    carriers = list(regions)
    # A source graphic may be stored as vertically adjacent raster tiles.
    # Sharing a caption requires a common parsed figure, aligned native edges,
    # an empty seam, and independently matching native/cloud caption text.
    matched_captions = [
        line for line in captions
        if any(obj.kind == "figure_caption"
               and containment(line.bbox, obj.bbox) >= .65
               and re.sub(r'\s+', '', normalize_text(obj.text)).startswith(
                   re.sub(r'\s+', '', normalize_text(line.text))[:12])
               for obj in objects)]
    maximal = [region for region in regions
               if not any(region != other and containment(region, other) == 1
                          for other in regions)]
    for figure in (obj for obj in objects if obj.kind == "figure"):
        tiles = sorted((region for region in maximal
                        if containment(region, figure.bbox) >= .7),
                       key=lambda region: (region[1], region[0]))
        chain = []
        for tile in tiles:
            if chain:
                previous = chain[-1]
                seam = (tile[0], previous[3], tile[2], tile[1])
                contiguous = (
                    abs(previous[0] - tile[0]) <= 1
                    and abs(previous[2] - tile[2]) <= 1
                    and 0 <= tile[1] - previous[3] <= 2
                    and not any(max(line.bbox[0], seam[0]) < min(line.bbox[2], seam[2])
                                and max(line.bbox[1], seam[1]) < min(line.bbox[3], seam[3])
                                for line in native))
                if not contiguous:
                    chain = []
            chain.append(tile)
            if len(chain) >= 2:
                carrier = union(chain)
                if (any(adjacent_caption(line, carrier) for line in matched_captions)
                        and not any(_caption_kind(line.text) == "figure_caption"
                                    and carrier[0] < (line.bbox[0] + line.bbox[2]) / 2 < carrier[2]
                                    and carrier[1] < (line.bbox[1] + line.bbox[3]) / 2 < carrier[3]
                                    for line in native)):
                    carriers.append(carrier)
    targets = [obj.bbox for obj in objects if obj.kind == "figure"]
    for region in regions:
        # A contained raster is a constituent of its captioned graphic carrier.
        # Keep every region for independent figure coverage and preserve native
        # text; only caption association may come from a containing carrier.
        if not any(adjacent_caption(line, parent)
                   for parent in carriers if containment(region, parent) == 1
                   for line in captions):
            return False
        intersections = [(max(region[0], other[0]), max(region[1], other[1]),
                          min(region[2], other[2]), min(region[3], other[3]))
                         for other in targets if area((max(region[0], other[0]), max(region[1], other[1]),
                                                     min(region[2], other[2]), min(region[3], other[3]))) > 0]
        if _union_area(intersections) < area(region) * 0.7:
            return False
    return True


def area(box):
    return max(0, box[2] - box[0]) * max(0, box[3] - box[1])


def containment(small, large):
    overlap = (max(0, min(small[2], large[2]) - max(small[0], large[0])) *
               max(0, min(small[3], large[3]) - max(small[1], large[1])))
    size = area(small)
    return overlap / size if size > 0 else 0.0


def union(boxes):
    return (min(box[0] for box in boxes), min(box[1] for box in boxes),
            max(box[2] for box in boxes), max(box[3] for box in boxes))


def _merge_contained(targets):
    result = []
    # Explicit layout bodies retain their identity when a supplementary
    # native raster envelope extends across them and neighbouring fragments.
    for obj in sorted(targets, key=lambda obj: (obj.role.startswith('native_'), -area(obj.bbox))):
        twin = next((i for i,other in enumerate(result)
                     if obj.role.startswith('native_') and not other.role.startswith('native_')
                     and other.kind == obj.kind and other.page_number == obj.page_number
                     and containment(other.bbox,obj.bbox) >= .93
                     and containment(obj.bbox,other.bbox) >= .85), None)
        if twin is not None:
            result[twin] = replace(result[twin], bbox=union([result[twin].bbox,obj.bbox]))
            continue
        if not any(other.kind == obj.kind and other.page_number == obj.page_number
                   and containment(obj.bbox, other.bbox) >= 0.93 for other in result):
            result.append(obj)
    return result


def _panel_group(targets, document, captions=()):
    """Connect consecutive subpanel labels in physical space, in either order.

    Labels inside a panel belong to that panel; a label between stacked rows
    normally belongs below the upper panel. Absolute y bands are not used.
    """
    from .caption_rules import _matches, _horizontal_overlap
    from .logical_objects import axis_unit, panel_label_lines, panel_owner_rank, remove_native_label_observations
    targets=remove_native_label_observations(targets,document,captions)
    pages = {page.number: page for page in document.pages}
    tags = {}
    external_tags = set()
    tag_boxes = defaultdict(list)
    # Learn label placement from unambiguous panels on this page. This
    # distinguishes a top-of-panel label from a label below the previous row.
    hints, votes = [], defaultdict(lambda: [0, 0])
    for page in pages.values():
        for line in panel_label_lines(page, targets, captions):
            tag = _panel_match(line.text)
            if not tag or axis_unit(line, targets, page):continue
            x=(line.bbox[0]+line.bbox[2])/2; y=(line.bbox[1]+line.bbox[3])/2
            candidates=[i for i,o in enumerate(targets) if o.kind in {'figure','table'}
                        and o.page_number==page.number and o.bbox[0]-15<=x<=o.bbox[2]+15
                        and o.bbox[1]-15<=line.bbox[3] and (line.bbox[1]<=o.bbox[3]+35 or (
                        y<=o.bbox[3]+65 and any(c.kind==o.kind+'_caption'
                          and c.page_number==page.number and 0<=c.bbox[1]-line.bbox[3]<=40
                          and _horizontal_overlap(o,c)>=.25 for c in captions)
                        and not any(o.bbox[3]+2<l.bbox[1] and l.bbox[3]<line.bbox[1]
                          and len(re.findall(r'[A-Za-z\u4e00-\u9fff]',l.text))>=12
                          and l.bbox[2]-l.bbox[0]>(o.bbox[2]-o.bbox[0])*.75 for l in page.lines)))]
            inside=[i for i in candidates if any(b[0]<=x<=b[2] and b[1]<=y<=b[3]
                    for b in (targets[i].panel_boxes or (targets[i].bbox,)))]
            unambiguous=inside if len(inside)==1 else candidates if len(candidates)==1 else []
            if len(unambiguous)==1:
                obj=targets[unambiguous[0]]
                physical=[b for b in (obj.panel_boxes or (obj.bbox,)) if b[0]<=x<=b[2]]
                if not physical:
                    physical=[b for b in (obj.panel_boxes or (obj.bbox,)) if b[0]-15<=x<=b[2]+15]
                if not physical:continue
                box=min(physical,key=lambda b:max(b[1]-y,y-b[3],0))
                fraction=(y-box[1])/max(1,box[3]-box[1])
                if fraction<=.25:votes[page.number][0]+=1
                elif fraction>=.75:votes[page.number][1]+=1
            hints.append((page.number,tag.group(1).lower(),x,y,candidates,line.bbox))
    for page_number,tag,x,y,candidates,label_box in hints:
        above=votes[page_number][0]>votes[page_number][1]
        ranked=[]
        for i in candidates:
            obj=targets[i]
            ranked.append((*panel_owner_rank(obj, targets, candidates, x, y, above, label_box), i))
        if ranked and min(ranked)[0] < 3:
            i=min(ranked)[-1];tags.setdefault(i,set()).add(tag)
            tag_boxes[i].append(label_box)
            if y>targets[i].bbox[3]:external_tags.add(i)
    def complete_namespace_title(first, second):
        """Original panels with one contiguous label namespace can wrap columns.

        A centred final row has no aligned column in the preceding row. Require
        physical panel evidence and a single common title instead of treating
        this ordinary layout as an independent figure. Repeated labels, titles
        between rows, and prose barriers retain their independent obligations.
        """
        from .object_identity import coverage
        left, right = targets[first], targets[second]
        proposed = replace(left, bbox=union([left.bbox,right.bbox]))
        title_options = [c for c in captions if c.kind==left.kind+'_caption'
                         and c.page_number==left.page_number and _matches(proposed,c)
                         and c.bbox[1]>=max(left.bbox[3],right.bbox[3])-5]
        for title in title_options:
            boundary = max((c.bbox[3] for c in captions
                            if c.kind==title.kind and c.page_number==title.page_number
                            and c.bbox[3]<title.bbox[1]-2),default=0)
            members = [i for i in tags if targets[i].kind==left.kind
                       and targets[i].page_number==left.page_number
                       and targets[i].bbox[1]>=boundary
                       and targets[i].bbox[3]<=title.bbox[1]+5]
            if first not in members or second not in members:continue
            letters = [tag for i in members for tag in tags[i]]
            ordered = sorted(letters)
            if len(letters)<3 or len(set(letters))!=len(letters):continue
            if ordered!=[chr(ord('a')+i) for i in range(len(ordered))]:continue
            boxes=[b for i in members for b in (targets[i].panel_boxes or (targets[i].bbox,))]
            page=pages[left.page_number]
            if not all(coverage(b,page.images+page.graphics)>=.8 for b in boxes):continue
            envelope=union([targets[i].bbox for i in members])
            width=envelope[2]-envelope[0]
            centre=abs((title.bbox[0]+title.bbox[2]-envelope[0]-envelope[2])/2)
            if centre<=width*.08 and _matches(replace(left,bbox=envelope),title):return True
        return False

    edges = []
    indices = list(tags)
    for offset, first in enumerate(indices):
        for second in indices[offset + 1:]:
            left, right = targets[first], targets[second]
            if left.page_number != right.page_number or left.kind != right.kind:
                continue
            consecutive = (ord(min(tags[first])) == ord(max(tags[second])) + 1
                           or ord(min(tags[second])) == ord(max(tags[first])) + 1)
            xgap = max(left.bbox[0] - right.bbox[2], right.bbox[0] - left.bbox[2], 0)
            ygap = max(left.bbox[1] - right.bbox[3], right.bbox[1] - left.bbox[3], 0)
            if not consecutive:continue
            if xgap>60:
                upper,lower=sorted((left,right),key=lambda o:o.bbox[1])
                # Alphabetical row-major numbering wraps from the last column
                # to the first. Verify the aligned columns on both physical rows.
                aligned_upper=any(o.kind==upper.kind and o.page_number==upper.page_number
                    and _horizontal_overlap(o,lower)>=.8
                    and min(o.bbox[3],upper.bbox[3])-max(o.bbox[1],upper.bbox[1])>=min(o.bbox[3]-o.bbox[1],upper.bbox[3]-upper.bbox[1])*.5 for o in targets)
                aligned_lower=any(o.kind==lower.kind and o.page_number==lower.page_number
                    and _horizontal_overlap(o,upper)>=.8
                    and min(o.bbox[3],lower.bbox[3])-max(o.bbox[1],lower.bbox[1])>=min(o.bbox[3]-o.bbox[1],lower.bbox[3]-lower.bbox[1])*.5 for o in targets)
                if not (aligned_upper and aligned_lower):
                    # The last row of a labelled composite may be incomplete.
                    # It still needs a full-width common title and a matching
                    # column in the preceding row; diagonal proximity is not enough.
                    envelope=union([left.bbox,right.bbox])
                    combined=replace(left,bbox=envelope)
                    common=any(c.kind==left.kind+'_caption' and c.page_number==left.page_number
                               and _matches(combined,c)
                               and c.bbox[2]-c.bbox[0]>=(envelope[2]-envelope[0])*.75
                               for c in captions)
                    if not ((aligned_upper and common and first in external_tags and second in external_tags)
                            or complete_namespace_title(first,second)):continue
            proposed = replace(left, bbox=union([left.bbox, right.bbox]))
            related = [c for c in captions if c.kind == left.kind+'_caption'
                       and c.page_number == left.page_number and _matches(proposed, c)]
            if ygap>62:
                # Stacked translated panel titles create a larger gutter.
                # Require two explicit outside panel labels and one centred
                # common academic title; proximity alone cannot join objects.
                box=proposed.bbox;width=box[2]-box[0]
                common=any(c.bbox[2]-c.bbox[0]>=width*.75
                           and abs((c.bbox[0]+c.bbox[2]-box[0]-box[2])/2)<=max(20,width*.08)
                           for c in related)
                relative_gap=min(left.bbox[3]-left.bbox[1],right.bbox[3]-right.bbox[1])*.4
                if not (ygap<=relative_gap and common and first in external_tags and second in external_tags):continue
            labelled_envelope=union([o.bbox for i,o in enumerate(targets) if i in tags and o.kind==left.kind and o.page_number==left.page_number])
            centred_title=any(abs((c.bbox[0]+c.bbox[2])-(labelled_envelope[0]+labelled_envelope[2]))/2
                              <=max(20,(labelled_envelope[2]-labelled_envelope[0])*.08) for c in related)
            if related and not centred_title and not (left.kind=="figure" and first in external_tags and second in external_tags) and not any(_horizontal_overlap(left, c) >= .25
                                   and _horizontal_overlap(right, c) >= .25 for c in related):
                continue
            upper, lower = sorted((left, right), key=lambda obj: obj.bbox[1])
            between = [line for line in pages[left.page_number].lines
                       if upper.bbox[3] <= line.bbox[1] <= lower.bbox[1]
                       and max(line.bbox[0], min(left.bbox[0], right.bbox[0])) <
                           min(line.bbox[2], max(left.bbox[2], right.bbox[2]))
                       and not _panel_match(line.text)
                       and not any(containment(line.bbox, box) >= .8
                                   for box in tag_boxes[first] + tag_boxes[second])
                       and (_caption_kind(line.text) or
                            (len(re.findall(r'[A-Za-z\u4e00-\u9fff]',line.text))>=12
                             and line.bbox[2]-line.bbox[0]>=min(left.bbox[2]-left.bbox[0],right.bbox[2]-right.bbox[0])*.75))]
            # Cloud titles and native text titles are equal physical
            # boundaries. A title missing from native extraction still keeps
            # independently captioned panels apart.
            between.extend(c for c in captions if c.page_number==left.page_number
                           and upper.bbox[3]<=c.bbox[1]<c.bbox[3]<=lower.bbox[1]
                           and max(c.bbox[0],min(left.bbox[0],right.bbox[0]))
                               <min(c.bbox[2],max(left.bbox[2],right.bbox[2])))
            if not between:
                xoverlap = max(0, min(left.bbox[2], right.bbox[2]) - max(left.bbox[0], right.bbox[0])) / max(1, min(left.bbox[2]-left.bbox[0], right.bbox[2]-right.bbox[0]))
                yoverlap = max(0, min(left.bbox[3], right.bbox[3]) - max(left.bbox[1], right.bbox[1])) / max(1, min(left.bbox[3]-left.bbox[1], right.bbox[3]-right.bbox[1]))
                edges.append((-max(xoverlap, yoverlap), xgap + ygap, first, second))
    # A second (a) starts a new composite. Components with duplicate labels
    # cannot merge, even if their image envelopes happen to be nearby.
    parents = list(range(len(targets)))
    labels = {i: set(tags.get(i, ())) for i in range(len(targets))}
    def root(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i
    # Choose maximum disjoint links at each alphabetical boundary. A greedy
    # cross-link between two restarted (a,b) groups can strand both true chains.
    boundaries=defaultdict(list)
    for axis,gap,first,second in sorted(edges):
        if ord(min(tags[first]))==ord(max(tags[second]))+1:first,second=second,first
        boundaries[max(tags[first])].append((axis,gap,first,second))
    chosen=[]
    for candidates in boundaries.values():
        adjacency=defaultdict(list);owners={}
        for _,_,left,right in candidates:adjacency[left].append(right)
        def link(left,seen):
            for right in adjacency[left]:
                if right in seen:continue
                seen.add(right)
                if right not in owners or link(owners[right],seen):
                    owners[right]=left;return True
            return False
        for left in adjacency:link(left,set())
        chosen.extend((left,right) for right,left in owners.items())
    for first,second in chosen:
        a,b=root(first),root(second)
        if a!=b and not labels[a].intersection(labels[b]):
            parents[b]=a;labels[a].update(labels[b])
    groups = defaultdict(list)
    for i in range(len(targets)):
        groups[root(i)].append(i)
    return [replace(targets[group[0]], bbox=union([targets[i].bbox for i in group]
        + [box for i in group for box in tag_boxes[i]] if len(group)>1
        else [targets[group[0]].bbox]),
        panel_boxes=tuple(b for i in group for b in (targets[i].panel_boxes or (targets[i].bbox,)))
        if len(group)>1 else targets[group[0]].panel_boxes) for group in groups.values()]


def _coalesce_image_boxes(boxes, figures=()):
    """Adjacent raster tiles are a single physical picture, not separate figures."""
    groups = []
    for box in boxes:
        related = []
        for index, group in enumerate(groups):
            if any((max(box[0]-other[2], other[0]-box[2], 0) <= .3
                    and min(box[3],other[3]) > max(box[1],other[1]))
                   or (max(box[1]-other[3],other[1]-box[3],0) <= .3
                       and min(box[2],other[2]) > max(box[0],other[0])) for other in group):
                related.append(index)
        combined = [box]
        for index in reversed(related):
            combined.extend(groups.pop(index))
        groups.append(combined)
    result=[]
    for group in groups:
        owners=set()
        for box in group:
            candidates=[(containment(box,obj.bbox),i) for i,obj in enumerate(figures)]
            if candidates and max(candidates)[0]>=.7:owners.add(max(candidates)[1])
        # Several explicit layout figures are separate objects even when they
        # touch. Merge raster fragments only for one independently parsed image.
        if len(owners)==1:result.append(union(group))
        else:result.extend(group)
    return tuple(result)


def caption_line_box(line):
    """Ignore isolated invalid font boxes using the title's own character evidence."""
    from statistics import median
    boxes = [b for _,_,b in line.text_regions if b[2]>b[0] and b[3]>b[1]]
    if len(boxes) < 5:
        return line.bbox
    height = median(b[3]-b[1] for b in boxes)
    stable = [b for b in boxes if b[3]-b[1] <= height*1.8]
    if len(stable) < len(boxes)*.8 or len(stable)==len(boxes):
        return line.bbox
    return union(stable)


def prepare_caption_layout(objects, document):
    """No paper IDs, mutation coordinates, or evaluation labels are consulted."""
    pages = {page.number: page for page in document.pages}
    # Native pixel proof identifies these export carriers before cloud layout
    # is used. An overlapping rectangle that also contains outside research
    # content keeps its ordinary caption obligation.
    objects = [obj for obj in objects if not any(
        containment(obj.bbox, box) >= .98
        for box in getattr(pages[obj.page_number], 'margin_barcodes', ()))]
    from .decorative_layers import remove_decorative_layers
    objects,document=remove_decorative_layers(objects,document)
    from .declared_code_figures import recover_declared_code_figures
    objects=recover_declared_code_figures(objects,document)
    from .logical_objects import recover_interface_figures, attach_plot_legends, recover_native_plot_legends
    objects = recover_interface_figures(objects, document)
    objects = recover_native_plot_legends(objects, document)
    objects = attach_plot_legends(objects, document)
    objects = reclassify_flow_diagrams(objects, document)
    excluded = nonresearch_pages(document)
    from .signature_ocr import recovery_regions
    from .administrative_continuations import native_continuation_regions, native_continuation_table
    administrative = {page.number: recovery_regions(previous,page)
                      for previous,page in zip(document.pages,document.pages[1:])}
    native_continuations = {page.number: native_continuation_regions(previous,page,objects)
                           for previous,page in zip(document.pages,document.pages[1:])}
    def administrative_object(obj):
        if native_continuation_table(obj,native_continuations.get(obj.page_number,())):
            return True
        regions=administrative.get(obj.page_number,())
        if not regions or obj.kind not in {'figure','table'}:return False
        if any(c.kind==obj.kind+'_caption' and c.page_number==obj.page_number
               and _matches(obj,c) for c in objects):return False
        clips=[(max(obj.bbox[0],b[0]),max(obj.bbox[1],b[1]),min(obj.bbox[2],b[2]),min(obj.bbox[3],b[3])) for b in regions]
        owned=_union_area([b for b in clips if area(b)>0])>=area(obj.bbox)*.9
        # A signature bitmap inside the verified administrative table belongs
        # to the table. Keep outside ink, partial overlaps and independently
        # titled figures subject to their ordinary research obligations.
        if obj.kind=='table' or owned:
            return owned
        # The full-page raster is a scanning canvas. Independently parsed
        # figures outside the administrative form remain separate targets.
        return (obj.bbox[2]-obj.bbox[0]>=obj.page_width*.85
                and obj.bbox[3]-obj.bbox[1]>=obj.page_height*.85
                and all(containment(b,obj.bbox)>=.95 for b in regions))
    from .caption_rules import _matches
    directory_lines = toc_line_keys(document)
    directory_regions = defaultdict(list)
    for number, box in directory_lines:
        directory_regions[number].append(box)
    def directory_caption(obj):
        return obj.kind.endswith("_caption") and (
            is_toc_line(obj.text) or any(containment(obj.bbox, box) >= .8
                for box in directory_regions[obj.page_number]))
    pages = {page.number: page for page in document.pages}
    def paragraph_caption(obj):
        return obj.kind.endswith('_caption') and any(
            line.source == 'native' and paragraph_start(line, pages[obj.page_number])
            and containment(line.bbox, obj.bbox) >= .65
            for line in pages[obj.page_number].lines)
    def recovered_caption_prefix(obj):
        return obj.kind=='figure' and any(line.source in {'local_caption_prefix_ocr','local_numbered_prefix_ocr'}
            and line.text_regions and containment(obj.bbox,line.text_regions[0][2])>=.8
            and containment(line.text_regions[0][2],obj.bbox)>=.7
            for line in pages[obj.page_number].lines)
    evidence = [obj for obj in objects if obj.page_number not in excluded
                and not recovered_caption_prefix(obj)
                and not paragraph_caption(obj)
                and not directory_caption(obj)
                and not (obj.kind in {"figure", "table"} and
                         in_margin(obj.bbox, obj.page_width, obj.page_height, pages[obj.page_number].display_rotation))]
    for page in document.pages:
        if page.number in excluded:
            continue
        for line in page.lines:
            kind = next((name+'_caption' for name in ('figure', 'table')
                         if contextual_caption(line, page, name,objects)), None)
            # Keep malformed numbers and explicit continuation labels available
            # to the missing-title rule, even though they have no valid ID.
            if kind is None and re.match(r'^\s*(?:图|Figure|Fig\.?|表|Table)\s*\.\d+\s+|^\s*续表|^\s*Table\s+.+[Cc]ontinued', normalize_text(line.text), re.I):
                kind = _caption_kind(line.text)
            if kind and (page.number, line.bbox) not in directory_lines:
                evidence.append(LayoutObject(kind, page.number, caption_line_box(line), line.text, page.width, page.height))
        image_boxes = _coalesce_image_boxes([box for box in page.images if not any(
            obj.kind == 'table' and obj.page_number == page.number and containment(box,obj.bbox)>=.93 for obj in objects)], [obj for obj in objects if obj.kind=='figure' and obj.page_number==page.number])
        for kind, boxes in (("figure", image_boxes), ("table", page.tables)):
            for box in boxes:
                if in_margin(box, page.width, page.height, page.display_rotation):
                    continue
                # A full-page scan is a page, not an academic figure.
                if (kind == "figure" and area(box) > page.width * page.height * 0.5
                        and text_covers_region(page.lines, box)):
                    continue
                if any(obj.page_number == page.number and obj.kind in {"figure", "table"}
                       and obj.kind != kind and containment(box, obj.bbox) >= 0.93
                       for obj in objects):
                    continue
                # Coalescing adjacent PDF image tiles must retain the actual
                # placements, so later ownership can prove this physical body.
                tiles = tuple(b for b in page.images if containment(b, box) >= .98) if kind == 'figure' else ()
                evidence.append(LayoutObject(kind, page.number, box, "", page.width, page.height,
                                             role='native_'+kind,
                                             panel_boxes=tiles if len(tiles) > 1 else ()))
    from .inline_equation_rasters import remove_inline_equation_rasters
    evidence=remove_inline_equation_rasters(evidence,document)
    evidence=[obj for obj in evidence if not administrative_object(obj)]
    from .administrative_layout_repair import repair_administrative_layout
    evidence=repair_administrative_layout(evidence,document)
    from .caption_identity import bilingual_alias_kind
    canonical=[]
    for obj in evidence:
        if obj.kind.endswith('_caption'):
            for line in pages[obj.page_number].lines:
                if normalize_text(line.text).strip()==normalize_text(obj.text).strip() and containment(line.bbox,obj.bbox)>=.8:
                    alias=bilingual_alias_kind(line,pages[obj.page_number],objects)
                    if alias:obj=replace(obj,kind=alias+'_caption')
                    break
        canonical.append(obj)
    from .caption_identity import reconcile_caption_bounds
    source_captions = [obj for obj in canonical if obj.kind.endswith('_caption')]
    evidence=reconcile_caption_bounds(canonical,document)
    from .graphic_containers import recover_declared_vector_panels
    evidence = recover_declared_vector_panels(evidence, document)
    from .container_ownership import reclassify_mixed_panels, recover_ruled_table_containers, recover_code_like_result_tables
    evidence = recover_code_like_result_tables(evidence, document)
    evidence = recover_ruled_table_containers(evidence, document)
    evidence = reclassify_mixed_panels(evidence, document)
    from .object_identity import refine_targets
    evidence = refine_targets(evidence, document)
    from .logical_objects import remove_native_fragments, shared_title_groups, shared_table_blocks, continuous_chart_rows, remove_embedded_targets, shared_axis_groups, complete_panel_envelopes, recover_native_raster_partitions
    targets = _merge_contained(remove_native_fragments(recover_native_raster_partitions(
        [obj for obj in evidence if obj.kind in {"figure", "table"}], document,
        [obj for obj in evidence if obj.kind.endswith('_caption')])))
    captions = _merge_contained([obj for obj in evidence if obj.kind.endswith("_caption")])
    from .logical_objects import reconcile_caption_alias_owners
    targets = reconcile_caption_alias_owners(targets, source_captions, document)
    captions = _caption_aliases(captions)
    from .logical_objects import reconcile_physical_rasters
    targets = reconcile_physical_rasters(targets, captions, document)
    from .graphic_annotations import recover_graphic_annotations
    document = recover_graphic_annotations(document, targets + captions)
    from .declared_composites import merge_declared_stacks
    targets = merge_declared_stacks(targets, captions, document)
    targets = continuous_chart_rows(targets, captions, document, before_labels=True)
    targets = shared_axis_groups(targets, captions, document)
    targets = _panel_group(targets, document, captions)
    targets = remove_embedded_targets(targets, captions, evidence)
    targets = continuous_chart_rows(targets, captions, document)
    targets = shared_title_groups(targets, captions, document)
    targets = shared_table_blocks(targets, captions, document)
    targets = complete_panel_envelopes(targets, captions, document)
    from .unnumbered_table_titles import recover_table_titles
    captions = recover_table_titles(targets, captions, document)
    # Strong panel/title evidence is resolved before residual physical frames.
    from .graphic_containers import merge_physical_graphic_containers
    targets = merge_physical_graphic_containers(targets, captions, document)
    from .graphic_containers import remove_internal_bitmap_fragments
    targets = remove_internal_bitmap_fragments(targets, captions, document)
    # Grouping can reconstruct an original tiled carrier after the first
    # reconciliation pass. Consume its duplicate parser fragments once.
    targets = reconcile_physical_rasters(targets, captions, document)
    from .caption_blocks import extend_panel_description_titles
    captions = extend_panel_description_titles(targets,captions,document)
    # Final identity passes preserve raw observations while joining only
    # independently declared physical objects and their verified fragments.
    from .table_identity_repair import repair_table_identity
    from .figure_identity_repair import repair_figure_identity
    prepared = targets + captions + [obj for obj in evidence if obj.kind == "text"]
    from .nonfigure_caption_carriers import repair_nonfigure_caption_carriers
    from .source_native_caption_ownership import repair_source_native_caption_ownership
    from .descriptive_caption_ownership import repair_descriptive_caption_ownership
    from .vector_strip_caption_ownership import repair_vector_strip_caption_ownership
    from .descriptive_annotation_ownership import repair_descriptive_annotation_ownership
    from .raster_marker_caption_ownership import repair_raster_marker_caption_ownership
    from .unlettered_caption_ownership import repair_unlettered_caption_ownership
    from .native_raster_observation_ownership import repair_native_raster_observation_ownership
    prepared = repair_nonfigure_caption_carriers(repair_table_identity(prepared, document), document)
    prepared = repair_figure_identity(prepared, document)
    prepared = repair_source_native_caption_ownership(prepared, document)
    prepared = repair_descriptive_caption_ownership(prepared, document)
    prepared = repair_vector_strip_caption_ownership(prepared, document)
    prepared = repair_descriptive_annotation_ownership(prepared, document)
    prepared = repair_raster_marker_caption_ownership(prepared, document)
    prepared = repair_unlettered_caption_ownership(prepared, document)
    return repair_native_raster_observation_ownership(prepared, document)


def _caption_aliases(captions):
    groups = []
    for obj in captions:
        pattern = FIGURE_CAPTION if obj.kind == "figure_caption" else TABLE_CAPTION
        match = pattern.search(normalize_text(obj.text))
        number = normalize_label(match.group("number")) if match else None
        duplicate = next((i for i, (old_number, old) in enumerate(groups)
                          if number is not None and number == old_number
                          and old.kind == obj.kind and old.page_number == obj.page_number
                          and abs(old.bbox[1] - obj.bbox[1]) <= 45
                          and max(old.bbox[0], obj.bbox[0]) < min(old.bbox[2], obj.bbox[2])), None)
        if duplicate is None:
            groups.append((number, obj))
        else:
            old_number, old = groups[duplicate]
            groups[duplicate] = (old_number, replace(old, bbox=union([old.bbox, obj.bbox])))
    return [obj for _, obj in groups]
