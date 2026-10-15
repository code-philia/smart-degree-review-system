from pathlib import Path
from pdf_rules.model import PdfDocument,PdfPage
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.layout_context import prepare_caption_layout


def run(text,caption=False):
    objects=[LayoutObject('table',1,(120,600,490,700),'',600,840,'native_table'),LayoutObject('text',1,(119,599,491,701),text,600,840,'code_body')]
    if caption:objects.append(LayoutObject('table_caption',1,(160,580,450,592),'表5.8 提示词模板',600,840))
    return [x for x in prepare_caption_layout(objects,PdfDocument(Path('template.pdf'),(PdfPage(1,600,840,()),))) if x.kind=='table']


def test_boxed_literal_prompt_is_not_a_native_table():
    assert run('Q&A Template\n{Question}\nPlease reason step by step and return the answer.')==[]


def test_structured_numeric_rows_are_not_discarded_as_prompt():
    assert len(run('Method Accuracy\nBase 85.4\nMinD 82.8'))==1


def test_explicitly_captioned_prompt_table_retains_table_identity():
    assert len(run('Q&A Template\n{Question}\nPlease reason step by step.',caption=True))==1
