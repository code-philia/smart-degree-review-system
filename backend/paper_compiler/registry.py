"""Reusable analysis contracts; rule identifiers are not capability names."""
import hashlib
from .storage import json_bytes
FIELD_TYPES={name:'string' for name in ['title','container','subtitle','type_code','carrier_code','year','volume','issue','pages','publisher','place','institution','conference','conference_year','date','access_date','url','doi','version','standard_number','patent_number','report_number','archive_number','scale','size','platform']}
FIELD_TYPES['authors']='array'
CAPABILITIES={
 'bibliography_order':{'version':'bibliography-order/1.0','targets':['BibliographyEntry'],'fields':{'position':'number','numeric_value':'number'},'description':'Position in bibliography and numeric entry label; nonnumeric labels give unknown numeric_value.'},
 'citation_order':{'version':'citation-order/1.0','targets':['ReferenceUse'],'fields':{'numeric_value':'number','first_appearance_rank':'number','is_first_use':'boolean'},'description':'Rank of first appearance of each distinct citation key, only known when citation source coverage is complete.'},
 'bibliography_fields':{'version':'bibliography-fields/1.0','targets':['BibliographyEntry'],'fields':FIELD_TYPES,'description':'Fields transcribed from the entry. Absent means absent from this text, not absent from the external work. Unknown extraction remains unknown.'},
 'bibliography_shape':{'version':'bibliography-shape/1.0','targets':['BibliographyEntry'],'fields':{'electronic':'boolean','type_bracketed':'boolean','label_bracketed':'boolean','system':'string','field_sequence':'array'},'description':'Observed notation and declared medium. system is numeric or author_year. DOI itself does not imply electronic medium. This capability does not return a rule verdict.'},
 'external_work':{'version':'external-work/1.0','targets':['BibliographyEntry'],'fields':{'exists':'boolean','available_fields':'array'},'description':'Publicly corroborated identity. Failed/empty searches remain UNKNOWN. available_fields describes metadata confirmed available on the verified work.'},
 'citation_syntax':{'version':'citation-syntax/1.0','targets':['CitationGroup'],'fields':{'system':'string','opening':'string','closing':'string','separators':'array','range_separators':'array','numbers':'array','automatic_footnote':'boolean'},'description':'Notation tokens, not conformance. Automatic-footnote status is unknown unless established from source.'},
 'citation_relevance':{'version':'citation-relevance/1.0','targets':['ReferenceUse'],'fields':{'related':'boolean'},'description':'This use purpose versus the identified work content. Supports methods, background, criticism, comparison and disagreement. Missing details/metadata or global topic mismatch are not negative proof.'}
}
REGISTRY={'version':'registry/'+hashlib.sha256(json_bytes(CAPABILITIES)).hexdigest()[:16],'capabilities':CAPABILITIES}
