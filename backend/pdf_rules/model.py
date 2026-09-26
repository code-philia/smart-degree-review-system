from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class PdfLine:
    page_number: int
    text: str
    bbox: tuple[float, float, float, float]
    page_width: float
    page_height: float


@dataclass(frozen=True)
class PdfPage:
    number: int
    width: float
    height: float
    lines: tuple[PdfLine, ...]
    unreadable: bool = False


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
    qualified: bool = False


@dataclass
class DocumentIndex:
    document: PdfDocument
    figures: list[Label] = field(default_factory=list)
    tables: list[Label] = field(default_factory=list)
    figure_refs: list[Label] = field(default_factory=list)
    table_refs: list[Label] = field(default_factory=list)
    appendices: list[Label] = field(default_factory=list)
    appendix_refs: list[Label] = field(default_factory=list)

    @property
    def lines(self) -> tuple[PdfLine, ...]:
        return self.document.lines

