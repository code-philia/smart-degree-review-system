from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class PdfLine:
    page_number: int
    text: str
    bbox: tuple[float, float, float, float]
    page_width: float
    page_height: float
    source: str = "native"
    role: str = ""
    text_regions: tuple[tuple[int, int, tuple[float, float, float, float]], ...] = ()
    reference_regions: tuple[tuple[int, int, tuple[float, float, float, float]], ...] = ()
    block_id: int | None = None
    direction: tuple[float, float] = (1.0, 0.0)
    font_size: float | None = None
    bold: bool = False


@dataclass(frozen=True)
class PdfPage:
    number: int
    width: float
    height: float
    lines: tuple[PdfLine, ...]
    unreadable: bool = False
    images: tuple[tuple[float, float, float, float], ...] = ()
    tables: tuple[tuple[float, float, float, float], ...] = ()
    ink_bottom: float | None = None
    legend_marks: tuple[tuple[float, float, float, float], ...] = ()
    display_rotation: int = 0
    graphics: tuple[tuple[float, float, float, float], ...] = ()
    margin_barcodes: tuple[tuple[float, float, float, float], ...] = ()


@dataclass(frozen=True)
class PdfDocument:
    path: Path
    pages: tuple[PdfPage, ...]

    @property
    def lines(self) -> tuple[PdfLine, ...]:
        return tuple(line for page in self.pages for line in page.lines)


@dataclass(frozen=True)
class Label:
    number: str
    line: PdfLine
    scope: str
    target_scope: str | None = None


@dataclass
class DocumentIndex:
    document: PdfDocument
    figures: list[Label] = field(default_factory=list)
    tables: list[Label] = field(default_factory=list)
    figure_refs: list[Label] = field(default_factory=list)
    table_refs: list[Label] = field(default_factory=list)
    graphic_figure_refs: list[Label] = field(default_factory=list)
    graphic_table_refs: list[Label] = field(default_factory=list)
    appendices: list[Label] = field(default_factory=list)
    appendix_refs: list[Label] = field(default_factory=list)

    @property
    def lines(self) -> tuple[PdfLine, ...]:
        return self.document.lines
