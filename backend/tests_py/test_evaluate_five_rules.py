import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from evaluate_five_rules import expected_sites, score_pair


class EvaluationTests(unittest.TestCase):
    def test_five_toc_edits_are_five_expected_sites(self):
        plan = {'plan': {'entries': [
            {'page': 7, 'top': 168 + i * 20, 'new_text': '3' if i < 3 else '7'}
            for i in range(5)]}}
        sites = expected_sites(28, plan)
        self.assertEqual(len(sites), 5)
        self.assertEqual(sites[0]['page'], 7)

    def test_score_excludes_preexisting_finding_and_counts_site_match(self):
        plan = {'plan': {'page': 32, 'new_marker': '(9.9)'}}
        mother = {'status': 'completed', 'findings': [
            {'page': 42, 'token': '2.1', 'bbox': [80, 100, 200, 115], 'text_excerpt': '原有引用(2.1)'}]}
        mutant = {'status': 'completed', 'findings': [
            {'page': 32, 'token': '9.9', 'bbox': [80, 100, 200, 115], 'text_excerpt': '公式(9.9)'},
            {'page': 42, 'token': '2.1', 'bbox': [80, 100, 200, 115], 'text_excerpt': '原有引用(2.1)'}]}
        scored = score_pair(18, plan, mother, mutant)
        self.assertEqual(scored['expected_sites'], 1)
        self.assertEqual(scored['detected_sites'], 1)
        self.assertEqual(scored['new_findings'], 1)
        self.assertEqual(scored['other_new_findings'], 0)
        self.assertEqual(scored['baseline_findings'], 1)

    def test_unsupported_mutant_counts_as_undetected(self):
        plan = {'plan': {'page': 13, 'new_marker': '[0]'}}
        scored = score_pair(22, plan, {'status': 'completed', 'findings': []},
                            {'status': 'unsupported', 'findings': [], 'reason': 'no references'})
        self.assertEqual(scored['expected_sites'], 1)
        self.assertEqual(scored['detected_sites'], 0)
        self.assertTrue(scored['unsupported'])

    def test_rule_6_site_uses_replacement_text_not_mother(self):
        plan = {'plan': {'abstract_page': 3, 'replacements': [
            {'page': 3, 'new_text': '这是一段被复制进摘要的正文内容'}]}}
        sites = expected_sites(6, plan)
        self.assertEqual(sites[0]['page'], 3)
        self.assertIn('被复制进摘要', sites[0]['text'])


    def test_duplicate_findings_do_not_inflate_precision(self):
        plan = {'plan': {'page': 13, 'new_marker': '[0]'}}
        duplicated = {'page': 13, 'token': '0', 'bbox': [80, 100, 120, 115],
                      'text_excerpt': '错误引用[0]'}
        scored = score_pair(22, plan, {'status': 'completed', 'findings': []},
                            {'status': 'completed', 'findings': [duplicated, duplicated.copy()]})
        self.assertEqual(scored['detected_sites'], 1)
        self.assertEqual(scored['matched_new_findings'], 1)
        self.assertEqual(scored['other_new_findings'], 1)


    def test_formula_site_preserves_dash_separator(self):
        plan = {'plan': {'page': 34, 'new_marker': '（9-9）'}}
        self.assertEqual(expected_sites(18, plan), [{'page': 34, 'token': '9-9'}])


    def test_baseline_match_tolerates_font_extraction_difference(self):
        plan = {'plan': {'page': 34, 'new_marker': '（9-9）'}}
        baseline = {'page': 34, 'token': '2-6', 'bbox': [85, 200, 400, 214],
                    'text_excerpt': '考代码长度𝑟的关系，如式（2-6）所示：'}
        unchanged = {'page': 34, 'token': '2-6', 'bbox': [85, 201, 400, 215],
                     'text_excerpt': '考代码长度r的关系，如式（2-6）所示：'}
        changed = {'page': 34, 'token': '9-9', 'bbox': [85, 240, 400, 254],
                   'text_excerpt': '公式如式（9-9）所示：'}
        scored = score_pair(18, plan, {'status': 'completed', 'findings': [baseline]},
                            {'status': 'completed', 'findings': [unchanged, changed]})
        self.assertEqual(scored['new_findings'], 1)
        self.assertEqual(scored['other_new_findings'], 0)


if __name__ == '__main__':
    unittest.main()
