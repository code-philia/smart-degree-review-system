import pytest
from pdf_rules.numbering import caption_match

@pytest.mark.parametrize("text,kind", [
    ("Figure 5.5 and Figure 5.6.", "figure"),
    ("Fig. 2.1, Fig. 2.2 and Fig. 2.3.", "figure"),
    ("Table 4.2 and Table 4.3.", "table"),
    ("图 2.1 与图 2.2。", "figure"),
    ("表 3.1、表 3.2。", "table"),
])
def test_reference_only_list_is_not_a_nominal_caption(text, kind):
    assert caption_match(text, kind) is None

@pytest.mark.parametrize("text,kind", [
    ("Figure 2.1 and Figure 2.2 Comparison of model outputs.", "figure"),
    ("Figure 5.5 Annotation Interface for Subjective Quality Experiment.", "figure"),
    ("表 2.1 与表 2.2 的实验设置对比", "table"),
])
def test_actual_title_after_numbered_subject_is_preserved(text, kind):
    assert caption_match(text, kind) is not None


@pytest.mark.parametrize("text,kind", [
    ("Figure 2.1 and Figure 2.2 show the results.", "figure"),
    ("Table 3.1 and Table 3.2 present the measurements.", "table"),
])
def test_coordinated_finite_body_predicate_is_not_a_nominal_title(text,kind):
    assert caption_match(text,kind) is None
