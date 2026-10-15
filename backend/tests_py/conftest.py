"""Keep all test modules bound to the currently assembled C7 runtime."""
from c7_runtime_ownership import install_import_guard, assert_runtime_ownership
from pathlib import Path

TESTS = Path(__file__).resolve().parent

install_import_guard()

def pytest_collection_modifyitems(session, config, items):
    assert_runtime_ownership()
    assert all(Path(item.path).resolve().is_relative_to(TESTS) for item in items)

def pytest_runtest_setup(item):
    assert_runtime_ownership()

def pytest_runtest_teardown(item, nextitem):
    assert_runtime_ownership()

def pytest_sessionfinish(session, exitstatus):
    assert_runtime_ownership()
