from pathlib import Path
import sys
import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from reference_verification_extract import extract, parse_entry


def test_gbt_english_title_is_not_an_author_initial():
    result = parse_entry('[12] VASWANI A, SHAZEER N, PARMAR N, et al. Attention is all you need[C]//Advances in Neural Information Processing Systems. 2017: 5998-6008.')
    assert result['title'] == 'Attention is all you need'
    assert result['year'] == 2017
    assert result['authors'][:2] == ['VASWANI A', 'SHAZEER N']
    assert result['extraction_confidence'] == 'high'


def test_quoted_ieee_title_and_doi_preserve_source():
    text = '[1] A. Smith and B. Doe, "A practical method for source checking," IEEE Access, 2024, doi: 10.1234/ABC.123.'
    result = parse_entry(text)
    assert result['title'] == 'A practical method for source checking'
    assert result['doi'] == '10.1234/abc.123'
    assert result['text'] == text


def test_apa_and_ambiguous_or_chinese_entries_are_explicit():
    assert parse_entry('Smith, J., & Doe, B. (2020). A robust test of scientific references. Nature, 12(1).')['title'] == 'A robust test of scientific references'
    zh = parse_entry('[2] 张三, 李四. 一种参考文献核验方法[J]. 计算机学报, 2023, 46: 1-9.')
    assert zh['title'] == '一种参考文献核验方法'
    assert zh['authors'] == ['张三', '李四']
    assert zh['year'] == 2023
    assert parse_entry('[3] This text has no reliably separated fields')['extraction_confidence'] == 'partial'


def test_initials_and_historical_title_years_do_not_create_metadata_conflicts():
    entry = parse_entry('[1] J. Smith, B. Doe. Reliable metadata verification for scholarly references[J]. Journal of Testing, 2023. doi:10.1234/reliable.')
    assert entry['title'] == 'Reliable metadata verification for scholarly references'
    assert entry['authors'] == ['J. Smith', 'B. Doe']
    history = parse_entry('[2] SMITH J. Review of computational methods from 1990 to 2010[J]. Journal of Testing, 2023.')
    assert history['year'] == 2023


def test_initial_author_comma_style_and_et_al_comma_boundaries():
    for text,title in [
        ('1. J. C. Ehlers, A. A. Feidenhans, et al., Affordable green hydrogen from alkaline water electrolysis, [J]. ACS Energy Letters, 2023.', 'Affordable green hydrogen from alkaline water electrolysis'),
        ('2. A. Raveendran, M. Chandran, and R. Dhanusuraman, A comprehensive review on electrochemical water splitting, [J]. RSC Advances, 2023.', 'A comprehensive review on electrochemical water splitting'),
        ('3. M.-T. Huang and P.-M. Zhai, Achieving Paris Agreement temperature goals, [J]. Advances in Climate Change Research, 2021.', 'Achieving Paris Agreement temperature goals'),
    ]:
        result=parse_entry(text)
        assert result['title']==title
        assert result['extraction_confidence']=='high'


def test_apa_question_title_does_not_absorb_journal_or_doi():
    result=parse_entry('Smith, J. (2023). Can we trust metadata verification for scholarly references? Journal of Testing, 12(1), 1-9. doi:10.1234/reliable.')
    assert result['title']=='Can we trust metadata verification for scholarly references?'
    assert result['doi']=='10.1234/reliable'


def test_native_cross_page_reference_has_only_its_own_locations(tmp_path):
    pdf = tmp_path / 'refs.pdf'
    document = pymupdf.open()
    p = document.new_page(width=600, height=800)
    p.insert_text((60, 90), 'References', fontsize=18)
    p.insert_text((60, 720), '[1] SMITH J. A robust reference checking method[J].', fontsize=11)
    p = document.new_page(width=600, height=800)
    p.insert_text((60, 80), 'Journal of Testing, 2023, 12: 1-9. doi:10.1234/test.1', fontsize=11)
    p.insert_text((60, 160), '[2] DOE J. A second independent method[J]. Testing, 2024.', fontsize=11)
    document.save(pdf)
    document.close()
    result = extract(pdf)
    assert len(result['entries']) == 2
    first, second = result['entries']
    assert first['doi'] == '10.1234/test.1'
    assert {r['page_number'] for r in first['location']['rects']} == {1, 2}
    assert {r['page_number'] for r in second['location']['rects']} == {2}
    assert result['native_only'] is True


def test_image_only_pages_do_not_become_successful_empty_bibliography(tmp_path):
    pdf = tmp_path / 'empty.pdf'
    document = pymupdf.open()
    document.new_page()
    document.save(pdf)
    document.close()
    result = extract(pdf)
    assert result['entries'] == []
    assert result['coverage_complete'] is False


def test_two_column_references_do_not_mix_authors_and_titles(tmp_path):
    pdf = tmp_path / 'columns.pdf'
    document = pymupdf.open()
    p = document.new_page(width=600, height=800)
    p.insert_text((30, 50), 'References', fontsize=16)
    for x, number, author in [(30, 1, 'SMITH J'), (320, 3, 'DOE B')]:
        p.insert_text((x, 100), f'[{number}] {author}. A correct reference', fontsize=10)
        for i, text in enumerate(['title and author belong together[J].', 'Journal of Testing, 2023.', 'Continuation with volume and pages.', 'This is more continuation text.']):
            p.insert_text((x, 115 + i * 12), text, fontsize=10)
        p.insert_text((x, 220), f'[{number+1}] {author}. The next reference[J].', fontsize=10)
        for i in range(4):
            p.insert_text((x, 235 + i * 12), 'Journal of Testing, 2024, 1: 1-9.', fontsize=10)
    document.save(pdf)
    document.close()
    entries = extract(pdf)['entries']
    assert len(entries) == 4
    assert entries[0]['text'].startswith('[1]')
    assert entries[1]['text'].startswith('[2]')
    assert entries[0]['authors'] == ['SMITH J']
    assert 'DOE B' not in entries[0]['text']
    assert 'title and author belong together' in entries[0]['text']


def test_short_two_column_bibliography_keeps_each_doi_with_its_entry(tmp_path):
    pdf = tmp_path / 'short-columns.pdf'
    document = pymupdf.open()
    p = document.new_page(width=600, height=800)
    p.insert_text((30, 50), 'References', fontsize=16)
    for x, n in [(30, 1), (320, 2)]:
        p.insert_text((x, 100), f'[{n}] SMITH J. Reference method {n}[J].', fontsize=10)
        p.insert_text((x, 115), 'Journal of Testing, 2023.', fontsize=10)
        p.insert_text((x, 130), f'doi:10.1234/source.{n}', fontsize=10)
    document.save(pdf)
    document.close()
    entries = extract(pdf)['entries']
    assert len(entries) == 2
    assert [e['doi'] for e in entries] == ['10.1234/source.1', '10.1234/source.2']
    assert all(len(set(r['x1'] < 300 for r in e['location']['rects'])) == 1 for e in entries)


def test_ambiguous_multiple_dois_do_not_verify_the_wrong_work():
    entry = parse_entry('[1] SMITH J. Mixed entry[J]. Journal, 2023. doi:10.1234/first doi:10.1234/second')
    assert entry['doi'] is None
    assert entry['extraction_confidence'] == 'partial'


def test_equivalent_escaped_doi_repetitions_keep_reliable_metadata():
    text = ('[5] BERKHOLZ C, GROHE M. Limitations of Algebraic Approaches to Graph Isomorphism Testing\n'
            '[C/OL]//Lecture Notes in Computer Science, 2015: 155-166.\n'
            'https://doi.org/10.1007/978-3-662-47672-7%5C_13. DOI: 10.1007/978-3-662-47672-7\\_13.')
    entry = parse_entry(text)
    assert entry['doi'] == '10.1007/978-3-662-47672-7_13'
    assert entry['extraction_confidence'] == 'high'
    assert entry['text'] == text


def test_wrapped_repeated_doi_is_not_a_second_identifier():
    entry = parse_entry('[13] OTTO M. Bounded Variable Logics and Counting[M/OL]. Cambridge, 2017.\n'
                        'https://doi.org/10.1017/9781316716878. DOI: 10.1017/978\n1316716878.')
    assert entry['doi'] == '10.1017/9781316716878'
    assert entry['extraction_confidence'] == 'high'


def test_a_following_publication_year_is_not_joined_to_a_complete_doi():
    entry = parse_entry('[1] SMITH J. A reliable reference[J]. Journal, 2023.\nDOI: 10.1234/source.1\n2024')
    assert entry['doi'] == '10.1234/source.1'


def test_wrapped_hyphenated_doi_and_equivalent_url_agree():
    entry = parse_entry('[20] DAWAR A, RICHERBY D. Counting Logics on Finite Structures[C/OL]. Springer, 2007. '
                        'https://doi.org/10.1007/978-3-540-74915-8%5C_10. DOI: 10.1007/978-3\n-540-74915-8\\_10.')
    assert entry['doi'] == '10.1007/978-3-540-74915-8_10'
    assert entry['extraction_confidence'] == 'high'


def test_native_legacy_sici_doi_preserves_registered_suffix_characters():
    doi = '10.1002/1097-0118(200011)35:3<222::aid-jgt7>3.0.co;2-e'
    entry = parse_entry(f'[1] SMITH J. A legacy graph theory article[J]. Journal, 2000. DOI: {doi}.')
    assert entry['doi'] == doi


def test_angle_wrapped_doi_does_not_keep_the_outer_bracket():
    entry = parse_entry('[1] SMITH J. A reliable scholarly article[J]. Journal, 2024. <https://doi.org/10.1234/source.1>')
    assert entry['doi'] == '10.1234/source.1'


def test_numeric_pagination_after_doi_is_not_an_identifier_continuation():
    entry = parse_entry('[1] SMITH J. A reliable scholarly article[J]. Journal, 2024. DOI: 10.1234/source.1\n1-9.')
    assert entry['doi'] == '10.1234/source.1'


def test_book_volume_qualifier_is_not_part_of_the_title():
    text = '[13] OTTO M. Bounded Variable Logics and Counting: A Study in Finite Models: vol. 9[M/OL]. Cambridge, 2017. DOI:10.1017/9781316716878.'
    entry = parse_entry(text)
    assert entry['title'] == 'Bounded Variable Logics and Counting: A Study in Finite Models'
    assert entry['text'] == text


def test_search_variants_require_a_physical_soft_wrap_and_preserve_source():
    text = '[7] ATSERIAS A, MANCINSKA L. Quantum and non-signalling graph iso-\nmorphisms[J]. Journal, 2019.'
    entry = parse_entry(text)
    assert entry['title'] == 'Quantum and non-signalling graph iso- morphisms'
    assert entry['title_search_variants'] == ['Quantum and non-signalling graph isomorphisms']
    assert entry['text'] == text
    unwrapped = parse_entry(text.replace('-\n', '- '))
    assert not unwrapped.get('title_search_variants')


def test_smaller_repeated_bibliography_continuations_keep_year_doi_and_location(tmp_path):
    pdf = tmp_path / 'smaller-reference-body.pdf'
    document = pymupdf.open()
    page = document.new_page(width=600, height=800)
    for y in range(100, 500, 20):
        page.insert_text((60, y), 'A normal main text paragraph.', fontsize=12)
    page.insert_text((60, 600), 'References', fontsize=18)
    page.insert_text((60, 720), '[1] SMITH J. First scholarly reference[J].', fontsize=10)
    for index in range(2):
        page = document.new_page(width=600, height=800)
        page.insert_text((60, 70), 'Journal of Testing, 2024, 1: 1-9.', fontsize=10)
        page.insert_text((60, 90), f'doi:10.1234/source.{index+1}', fontsize=10)
        if index == 0:
            page.insert_text((60, 680), '[2] DOE J. Second scholarly reference[J].', fontsize=10)
    document.save(pdf); document.close()
    entries = extract(pdf)['entries']
    assert len(entries) == 2
    assert [entry['year'] for entry in entries] == [2024, 2024]
    assert [entry['doi'] for entry in entries] == ['10.1234/source.1', '10.1234/source.2']
    assert any(rect['page_number'] == 2 and rect['y1'] < 70 for rect in entries[0]['location']['rects'])


def test_repeated_running_margins_are_not_reference_text_or_locations(tmp_path):
    pdf = tmp_path / 'running-margins.pdf'
    document = pymupdf.open()
    for index in range(2):
        page = document.new_page(width=600, height=800)
        page.insert_text((60, 70), 'References', fontsize=9)
        page.insert_text((400, 70), 'University thesis', fontsize=9)
        if index == 0:
            page.insert_text((60, 130), 'References', fontsize=18)
            page.insert_text((60, 670), '[1] SMITH J. A robust scholarly reference[J].', fontsize=11)
            page.insert_text((60, 690), 'Journal of Testing, 2023, 1: 1-9.', fontsize=11)
        else:
            page.insert_text((60, 130), '[2] DOE J. An independent scholarly reference[J].', fontsize=11)
            page.insert_text((60, 150), 'Journal of Testing, 2024, 2: 10-19.', fontsize=11)
        page.insert_text((295, 750), str(43+index), fontsize=9)
    document.save(pdf); document.close()
    entries = extract(pdf)['entries']
    assert len(entries) == 2
    assert 'University thesis' not in entries[0]['text']
    assert '\n43' not in entries[0]['text']
    assert {r['page_number'] for r in entries[0]['location']['rects']} == {1}
    assert all(r['y1'] > 100 and r['y2'] < 730 for entry in entries for r in entry['location']['rects'])


def test_author_year_entries_starting_on_next_page_remain_separate(tmp_path):
    pdf=tmp_path/'apa-pages.pdf'
    document=pymupdf.open()
    for index,author in enumerate(['Smith','Doe']):
        p=document.new_page(width=600,height=800)
        if index==0:p.insert_text((60,80),'References',fontsize=16)
        p.insert_text((60,150),f'{author}, J. (202{index+3}). A reliable scholarly reference.',fontsize=11)
        p.insert_text((60,170),f'Journal of Testing. doi:10.1234/source.{index+1}',fontsize=11)
    document.save(pdf);document.close()
    entries=extract(pdf)['entries']
    assert len(entries)==2
    assert [e['doi'] for e in entries]==['10.1234/source.1','10.1234/source.2']
    assert [e['location']['page_number'] for e in entries]==[1,2]


def test_publication_list_after_references_does_not_extend_the_last_entry(tmp_path):
    pdf=tmp_path/'backmatter.pdf'
    document=pymupdf.open()
    p=document.new_page(width=600,height=800)
    for y,text in [(80,'References'),(130,'[1] SMITH J. A correct reference[J]. Journal, 2023.'),(210,'List of Publications'),(240,'As first author:'),(270,'1) A different unpublished paper, 2026.')]:
        p.insert_text((60,y),text,fontsize=16 if y in [80,210] else 11)
    document.save(pdf);document.close()
    entries=extract(pdf)['entries']
    assert len(entries)==1
    assert 'List of Publications' not in entries[0]['text']
    assert all(r['y2']<180 for r in entries[0]['location']['rects'])
