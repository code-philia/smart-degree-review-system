"""Pure evidence for local computational subgraph names, never figure IDs."""
import re
from .numbering import normalize_text, normalize_label

_NAME=r'[A-Z]\s*[0-9]+(?![A-Za-z0-9_.\-])'
_PROGRAM=r'[A-Za-z_][A-Za-z0-9_]*(?![A-Za-z0-9_])'
_FIGURE=r'(?:[A-Z]\.?)?[0-9]+(?:[.\-][0-9]+)*'

class GraphSymbols(set):
    def __init__(self,document):
        super().__init__()
        self.legacy=set()
        # SQL keywords are insensitive; program identities are exact names.
        declaration=re.compile(r'(?i:\bCREATE\s+PROCEDURE)\s+(?P<name>'+_PROGRAM+r')\s*\(')
        self.procedures={m.group('name') for line in document.lines
                         for m in declaration.finditer(normalize_text(line.text))}
        # Retain exact original-line ownership of wrapped evidence. A later
        # parser may revisit those physical lines independently; the term must
        # still bind its complete node/program declaration without borrowing
        # evidence from another page or a different occurrence of the number.
        from .usage_paragraphs import usage_paragraphs
        by_page={p.number:p.lines for p in document.pages}
        self.contexts={}
        for paragraph,_ in usage_paragraphs([(l,'definition') for l in document.lines],document):
            context=normalize_text(paragraph.text)
            if not re.search(r'子\s*图\s*[0-9]',context):continue
            for original in by_page[paragraph.page_number]:
                if original.source!=paragraph.source:continue
                box=original.bbox;outer=paragraph.bbox
                if not (outer[0]<=box[0] and outer[1]<=box[1] and box[2]<=outer[2] and box[3]<=outer[3]):continue
                text=normalize_text(original.text)
                offset=context.find(text)
                if offset<0 or context.find(text,offset+1)>=0:continue
                self.contexts[(original.page_number,original.source,box,text)]=(context,offset)

    def add_tuple_symbol(self,symbol):
        self.add(symbol);self.legacy.add(symbol)

    def contains_number(self,number):
        # Preserve the pre-existing tuple-definition normalization contract.
        return number in self or normalize_label(number) in self.legacy

    def contextual_subgraph_use(self,text,match,line):
        context=self.contexts.get((line.page_number,line.source,line.bbox,normalize_text(line.text)))
        if context is None:return False
        whole,offset=context
        # Number separator normalization elsewhere must not move this token.
        if text!=normalize_text(line.text):return False
        from .numbering import FIGURE_REFERENCE
        from .reference_groups import reference_matches
        from .reference_context import _explicit_graph_reference
        for candidate in reference_matches(FIGURE_REFERENCE,whole):
            if (candidate.start('number')==offset+match.start('number')
                    and candidate.end('number')==offset+match.end('number')
                    and not _explicit_graph_reference(whole,candidate)):
                return local_subgraph_use(whole,candidate,self)
        return False


def local_subgraph_use(text,match,defined):
    before=text[:match.start()];after=text[match.end():]
    if not re.search(r'子\s*$',before) or not re.fullmatch(r'[0-9]+',match.group('number')):return False
    # A decomposition names graph components by node membership. A normal
    # numbered subpanel lacks both the graph decomposition and its operands.
    split=re.search(r'(?:依赖关系|计算|数据流|控制流)图[^。;；]{0,48}(?:分割|分解)(?:成|为)[^。;；]{0,24}子图',before)
    membership=re.match(r'\s*(?:包含|包含了)\s*从\s*'+_NAME+r'\s*(?:到|至)\s*'+_NAME+r'[^。;；]{0,16}节点',after)
    singleton=re.match(r'\s*(?:则)?\s*被转换为(?:了)?\s*'+_NAME+r'\s*(?:这)?(?:一个|一组)?节点',after)
    if split and (membership or singleton):return True
    # Procedure conversion inherits the local component namespace from the
    # explicitly cited graph split, and must bind an actual declared program.
    owner=re.search(r'图\s*'+_FIGURE+r'\s*中分割出的[^。;；]{0,12}子图所合成的存储过程',before)
    converted=re.match(r'\s*(?:则)?\s*被转换为(?:了)?\s*(?:名为)?(?P<name>'+_PROGRAM+r')(?=\s*(?:的存储过程|[（(]))',after)
    return bool(owner and converted and converted.group('name') in getattr(defined,'procedures',()))
