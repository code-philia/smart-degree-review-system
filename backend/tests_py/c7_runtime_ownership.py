"""Test-only guard: every real pdf_rules import must belong to C7."""
from pathlib import Path
import importlib.abc
import importlib.machinery
import sys

RUNTIME = (Path(__file__).resolve().parents[1] / 'pdf_rules').resolve()

def assert_runtime_ownership():
    import pdf_rules
    assert Path(pdf_rules.__file__).resolve().parent == RUNTIME, pdf_rules.__file__
    assert [Path(p).resolve() for p in pdf_rules.__path__] == [RUNTIME], list(pdf_rules.__path__)
    for name, module in tuple(sys.modules.items()):
        if name == 'pdf_rules' or name.startswith('pdf_rules.'):
            origin = getattr(module, '__file__', None)
            if origin is not None:
                assert Path(origin).resolve().is_relative_to(RUNTIME), (name, origin, str(RUNTIME))

class CandidateImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname != 'pdf_rules' and not fullname.startswith('pdf_rules.'):
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is not None and spec.origin is not None:
            assert Path(spec.origin).resolve().is_relative_to(RUNTIME), (fullname, spec.origin, str(RUNTIME))
        return spec

def install_import_guard():
    if not any(isinstance(x, CandidateImports) for x in sys.meta_path):
        sys.meta_path.insert(0, CandidateImports())
    assert_runtime_ownership()

