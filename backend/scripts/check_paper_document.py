"""Local document admission only; never import detector or model clients."""
import json
import hashlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paper_compiler.document_admission import DocumentAdmissionError, VERSION
from paper_compiler.frontend import build_paper


def check_document(pdf):
    """Only a fully built and contract-validated Paper earns a compiled proof."""
    digest = hashlib.sha256(Path(pdf).read_bytes()).hexdigest()
    try:
        ir = build_paper(Path(pdf), include_citations=False)
        return {**ir['metadata']['document_admission'], 'sha256': digest, 'compiled': True}
    except DocumentAdmissionError as error:
        return {**error.assessment, 'sha256': digest, 'compiled': False}
    except Exception:
        return {'version': VERSION, 'status': 'rejected', 'stage': 'compilation',
                'reason_code': 'paper_model_compile_failed', 'sha256': digest, 'compiled': False,
                'reason': 'PDF 无法完成 Paper Model 构建和结构校验；本次未执行任何论文规则。'}

if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit(2)
    print(json.dumps(check_document(sys.argv[1]), ensure_ascii=True))
