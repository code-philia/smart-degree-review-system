"""Usage-only physical parent/subfigure identities, without caption rewrites."""
import re

from .numbering import caption_match, normalize_text
from .usage_scope import usage_epoch, is_body_usage_scope
from .usage_reference_evidence import usage_resolved_target


def _box(box):
    from .usage_graphic_ocr import _box as checked
    return checked(box)


def _inside(box, outer):
    return outer[0]-.5 <= box[0] < box[2] <= outer[2]+.5 and outer[1]-.5 <= box[1] < box[3] <= outer[3]+.5


def _serial(number):
    match = re.fullmatch(r'(\d+(?:\.\d+)*)\.(\d+)', number)
    return (match[1], int(match[2])) if match else None


def _image(label, page):
    box = label.line.bbox
    center = (box[0]+box[2])/2
    hits = []
    for raw in (*page.images, *page.graphics):
        image = _box(raw)
        if image is None or image[2]-image[0] < 60 or image[3]-image[1] < 30:
            continue
        gap = box[1]-image[3]
        if (0 <= gap <= max(20, 2.5*(label.line.font_size or 10))
                and image[0] < center < image[2]
                and abs(center-(image[0]+image[2])/2) <= .25*(image[2]-image[0])):
            hits.append((gap, image))
    hits = sorted(set(hits))
    if not hits or (len(hits)>1 and abs(hits[0][0]-hits[1][0])<2):
        return None
    return hits[0][1]


def _native_reference(reference, parent, index, scopes):
    if reference.line.source != 'native' or usage_epoch(scopes, reference) != usage_epoch(scopes, parent):
        return False
    text = normalize_text(reference.line.text)
    number = re.escape(parent.number).replace(r'\.',r'[.\-]')
    pointer = re.compile(r'(?:图|Figures?|Figs?\.?)\s*'+number+r'(?![\d.\-])',re.I)
    whole = False
    for clause in re.split(r'[;；。!?！？]',text):
        if re.search(r'(?:左|右|上|下)(?:侧|半|边)?(?:的)?(?:图|子图)|(?:子图|panel)\s*\(?[a-h]\)?',clause,re.I):
            continue
        for match in pointer.finditer(clause):
            if not re.match(r'\s*(?:\([a-z]\)|[a-z](?![A-Za-z0-9]))',clause[match.end():],re.I):
                whole = True
    if not whole:
        return False
    def prose_role(row):
        return not re.search(r'(?:^|[\s_])(?:caption|figure_caption|table_caption|reference|bibliography|heading|toc|header|footer)(?:$|[\s_])',row.role.lower())
    if not prose_role(reference.line):
        return False
    page = next((p for p in index.document.pages if p.number==reference.line.page_number), None)
    return bool(page and any(row.source=='native' and not row.bold and prose_role(row)
        and _inside(reference.line.bbox, row.bbox)
        and is_body_usage_scope(scopes, row)
        and not caption_match(row.text, 'figure')
        and not any(_inside(row.bbox, image) for image in (*page.images, *page.graphics))
        for row in page.lines))


def _layout(parent, members, page):
    if len(members)<2 or _image(parent, page) is not None:
        return False
    members = sorted(members, key=lambda member:(member[1].line.bbox[1],member[1].line.bbox[0]))
    rows = []
    for member in members:
        if not rows or abs(member[1].line.bbox[1]-rows[-1][0][1].line.bbox[1])>5:
            rows.append([])
        rows[-1].append(member)
    width = len(rows[0])
    if not 2 <= width <= 4 or any(len(row)!=width for row in rows):
        return False
    for row in rows:
        if max(m[2][1] for m in row)-min(m[2][1] for m in row)>12:
            return False
        for left,right in zip(row,row[1:]):
            gap = right[2][0]-left[2][2]
            if not 0 <= gap <= .5*min(left[2][2]-left[2][0],right[2][2]-right[2][0]):
                return False
    for above,below in zip(rows,rows[1:]):
        if not 0 <= min(m[2][1] for m in below)-max(m[1].line.bbox[3] for m in above) <= 50:
            return False
        for first,second in zip(above,below):
            if abs(sum(first[2][::2])/2-sum(second[2][::2])/2)>20:
                return False
    images = [m[2] for m in members]
    bounds = (min(b[0] for b in images),min(b[1] for b in images),max(b[2] for b in images),parent.line.bbox[3])
    lowest = max(m[1].line.bbox[3] for m in members)
    if not 0 <= parent.line.bbox[1]-lowest <= 30:
        return False
    if abs((parent.line.bbox[0]+parent.line.bbox[2]-bounds[0]-bounds[2])/2)>max(16,.05*(bounds[2]-bounds[0])):
        return False
    if any(_inside(raw,bounds) and not any(_inside(raw,image) for image in images)
           for raw in (*page.images,*page.graphics)):
        return False
    captions = [m[1].line.bbox for m in members]+[parent.line.bbox]
    for row in page.lines:
        b = row.bbox
        if b[1] < bounds[1] or b[3] > bounds[3]+.5 or b[2] <= bounds[0] or b[0] >= bounds[2]:
            continue
        if not any(_inside(b, image) for image in images) and not any(_inside(b, caption) for caption in captions):
            return False
    return True


def composite_figure_usage_evidence(index, groups, scopes):
    """Credit only physically nested parallel panels with a whole-parent use.

    A numbered caption below a regular image grid can be a total caption even
    when the author numbers the individual panels. Number order alone never
    proves containment. Keep native labels, regions and reference facts intact.
    """
    pages = {p.number:p for p in index.document.pages}
    targets = [t for group in groups for t in group]
    answer = {}
    claims = {}
    for parent_group in groups:
        if len(parent_group)!=1:
            continue
        parent = parent_group[0]
        serial = _serial(parent.number)
        if serial is None or parent.line.source!='native' or not is_body_usage_scope(scopes, parent):
            continue
        references = [ref for ref in index.figure_refs
            if usage_resolved_target(ref,parent,targets,scopes)
            and _native_reference(ref,parent,index,scopes)]
        if not references:
            continue
        # An unqualified number shared by distinct objects cannot establish a
        # unique parent identity for the children.
        if any(sum(any(usage_resolved_target(ref,t,targets,scopes) for t in group)
                   for group in groups)!=1 for ref in references):
            continue
        page = pages[parent.line.page_number]
        members = []
        for number in range(serial[1]-1, max(-1,serial[1]-9), -1):
            matches = [(i,group[0]) for i,group in enumerate(groups) if len(group)==1
                       and group[0].number==f'{serial[0]}.{number}'
                       and group[0].line.page_number==page.number
                       and is_body_usage_scope(scopes,group[0])
                       and usage_epoch(scopes,group[0])==usage_epoch(scopes,parent)]
            if len(matches)!=1:
                break
            ordinal,child = matches[0]
            image = _image(child,page)
            if image is None or child.line.source!='native' or child.line.bbox[3]>parent.line.bbox[1]:
                break
            members.append((ordinal,child,image))
        if not _layout(parent,members,page):
            continue
        for ordinal,child,image in members:
            proof = dict(kind='physical_composite_parent_reference',
                child=dict(number=child.number,page=page.number,bbox=list(child.line.bbox),image_bbox=list(image)),
                parent=dict(number=parent.number,page=page.number,bbox=list(parent.line.bbox)),
                references=[dict(page=r.line.page_number,bbox=list(r.line.bbox),text=r.line.text) for r in references],
                epoch=usage_epoch(scopes,parent))
            if ordinal in claims:
                answer.pop(ordinal,None)
            else:
                answer[ordinal]=proof
            claims.setdefault(ordinal,set()).add((parent.number,parent.line.bbox))
    return answer
