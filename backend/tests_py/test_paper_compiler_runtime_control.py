"""Atomic runtime release controls; all artifacts live in pytest tmp_path."""
import importlib
import importlib.util
import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest


def api():
    assert importlib.util.find_spec("paper_compiler.runtime_control") is not None, "runtime control is not implemented"
    return importlib.import_module("paper_compiler.runtime_control")


def candidate(tmp_path, version):
    folder = tmp_path / "packages" / version
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(json.dumps({
        "schema_version": "paper-program/2.0", "version_id": version,
        "code_sha256": "a" * 64, "model_sha256": "b" * 64, "inputs_sha256": "c" * 64,
    }))
    (folder / "validation.json").write_text(json.dumps({"status": "passed"}))
    (folder / "checks.py").write_text("# validated by the separate program validator\n")
    return folder


def test_default_state_and_freeze_are_persistent(tmp_path):
    control = api().RuntimeControl(tmp_path / "runtime")
    assert control.snapshot() == {"freeze": False, "generation": 0, "active_version": None, "active_path": None}
    assert control.events() == []
    assert control.set_freeze(True, actor="operator")["generation"] == 1
    reopened = api().RuntimeControl(tmp_path / "runtime")
    assert reopened.snapshot() == {"freeze": True, "generation": 1, "active_version": None, "active_path": None}
    assert reopened.set_freeze(True)["generation"] == 1
    assert reopened.set_freeze(False)["generation"] == 2
    events = reopened.events()
    assert [event["action"] for event in events] == ["set_freeze", "set_freeze"]
    assert [event["freeze"] for event in events] == [True, False]
    assert [event["generation"] for event in events] == [1, 2]
    assert events[0]["actor"] == "operator"
    assert events[0]["created_at"]


@pytest.mark.parametrize("invalid", [0, 1, "true", None, [], {}])
def test_freeze_rejects_non_boolean_without_mutation(tmp_path, invalid):
    control = api().RuntimeControl(tmp_path / "runtime")
    with pytest.raises(TypeError):
        control.set_freeze(invalid)
    assert control.snapshot()["generation"] == 0
    assert control.events() == []


def test_promotion_preserves_absolute_path_and_release_history(tmp_path, monkeypatch):
    module = api()
    control = module.RuntimeControl(tmp_path / "runtime")
    first = candidate(tmp_path, "v1")
    original = {p.name: p.read_bytes() for p in first.iterdir()}
    monkeypatch.chdir(tmp_path)
    state = control.promote("v1", Path("packages/v1"), None, expected_generation=0, actor="research-loop")
    assert state == {"freeze": False, "generation": 1, "active_version": "v1", "active_path": str(first.resolve())}
    second = candidate(tmp_path, "v2")
    assert control.promote("v2", second, "v1", expected_generation=1)["generation"] == 2
    assert {p.name: p.read_bytes() for p in first.iterdir()} == original
    events = module.RuntimeControl(tmp_path / "runtime").events()
    assert [event["action"] for event in events] == ["promote", "promote"]
    assert [(event["from_version"], event["to_version"]) for event in events] == [(None, "v1"), ("v1", "v2")]
    assert events[0]["actor"] == "research-loop"
    assert events[0]["active_path"] == str(first.resolve())


def test_frozen_runtime_rejects_an_already_prepared_candidate(tmp_path):
    module = api()
    control = module.RuntimeControl(tmp_path / "runtime")
    prepared = candidate(tmp_path, "v1")
    control.set_freeze(True)
    before = control.snapshot(), control.events()
    with pytest.raises(module.RuntimeFrozen):
        control.promote("v1", prepared, None, expected_generation=0)
    assert (control.snapshot(), control.events()) == before


@pytest.mark.parametrize("expected_version, expected_generation", [(None, None), ("v1", 0), ("wrong", 1)])
def test_stale_version_or_generation_cannot_promote(tmp_path, expected_version, expected_generation):
    module = api()
    control = module.RuntimeControl(tmp_path / "runtime")
    control.promote("v1", candidate(tmp_path, "v1"), None)
    second = candidate(tmp_path, "v2")
    before = control.snapshot(), control.events()
    with pytest.raises(module.VersionConflict):
        control.promote("v2", second, expected_version, expected_generation=expected_generation)
    assert (control.snapshot(), control.events()) == before


def test_generation_rejects_stale_candidate_after_freeze_unfreeze(tmp_path):
    module = api()
    control = module.RuntimeControl(tmp_path / "runtime")
    prepared = candidate(tmp_path, "v1")
    control.set_freeze(True)
    control.set_freeze(False)
    with pytest.raises(module.VersionConflict):
        control.promote("v1", prepared, None, expected_generation=0)
    assert control.snapshot()["active_version"] is None
    assert control.snapshot()["generation"] == 2


@pytest.mark.parametrize("broken", ["missing_directory", "missing_manifest", "bad_json", "array_manifest", "wrong_version", "missing_validation", "invalid_validation", "not_passed"])
def test_invalid_candidate_is_never_registered(tmp_path, broken):
    control = api().RuntimeControl(tmp_path / "runtime")
    folder = candidate(tmp_path, "v1")
    if broken == "missing_directory":
        shutil.rmtree(folder)
    elif broken == "missing_manifest":
        (folder / "manifest.json").unlink()
    elif broken == "bad_json":
        (folder / "manifest.json").write_text("{bad")
    elif broken == "array_manifest":
        (folder / "manifest.json").write_text("[]")
    elif broken == "wrong_version":
        (folder / "manifest.json").write_text(json.dumps({"version_id": "v2"}))
    elif broken == "missing_validation":
        (folder / "validation.json").unlink()
    elif broken == "invalid_validation":
        (folder / "validation.json").write_text("[]")
    else:
        (folder / "validation.json").write_text(json.dumps({"status": "failed"}))
    with pytest.raises(ValueError):
        control.promote("v1", folder, None)
    assert control.snapshot()["generation"] == 0
    assert control.events() == []


def test_rollback_is_explicit_and_allowed_while_frozen(tmp_path):
    module = api()
    control = module.RuntimeControl(tmp_path / "runtime")
    first = candidate(tmp_path, "v1")
    control.promote("v1", first, None)
    control.promote("v2", candidate(tmp_path, "v2"), "v1")
    control.set_freeze(True)
    reopened = module.RuntimeControl(tmp_path / "runtime")
    state = reopened.rollback("v1", actor="authorized-operator")
    assert state == {"freeze": True, "generation": 4, "active_version": "v1", "active_path": str(first.resolve())}
    event = reopened.events()[-1]
    assert event["action"] == "rollback"
    assert event["from_version"] == "v2" and event["to_version"] == "v1"
    assert event["actor"] == "authorized-operator" and event["freeze"] is True


def test_rollback_rejects_unpromoted_or_missing_versions(tmp_path):
    module = api()
    control = module.RuntimeControl(tmp_path / "runtime")
    candidate(tmp_path, "unpromoted")
    with pytest.raises(module.VersionConflict):
        control.rollback("unpromoted")
    first = candidate(tmp_path, "v1")
    control.promote("v1", first, None)
    control.promote("v2", candidate(tmp_path, "v2"), "v1")
    shutil.rmtree(first)
    before = control.snapshot(), control.events()
    with pytest.raises(ValueError):
        control.rollback("v1")
    assert (control.snapshot(), control.events()) == before


def test_registered_version_cannot_be_rebound_to_another_directory(tmp_path):
    module = api()
    control = module.RuntimeControl(tmp_path / "runtime")
    first = candidate(tmp_path, "v1")
    control.promote("v1", first, None)
    replacement = tmp_path / "replacement"
    shutil.copytree(first, replacement)
    before = control.snapshot(), control.events()
    with pytest.raises(module.VersionConflict):
        control.promote("v1", replacement, "v1")
    assert (control.snapshot(), control.events()) == before


def test_simultaneous_promotions_have_one_cas_winner(tmp_path):
    module = api()
    root = tmp_path / "runtime"
    first = candidate(tmp_path, "v1")
    second = candidate(tmp_path, "v2")
    barrier = Barrier(2)

    def attempt(version, folder):
        control = module.RuntimeControl(root)
        barrier.wait(timeout=10)
        try:
            return control.promote(version, folder, None, expected_generation=0)["active_version"]
        except module.VersionConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(attempt, "v1", first), pool.submit(attempt, "v2", second)]
        results = [future.result(timeout=20) for future in futures]
    assert results.count("conflict") == 1
    final = module.RuntimeControl(root)
    assert final.snapshot()["generation"] == 1
    assert final.snapshot()["active_version"] in {"v1", "v2"}
    assert len(final.events()) == 1


@pytest.mark.parametrize("invalid", [True, -1, "0", 1.5])
def test_generation_precondition_requires_nonnegative_integer(tmp_path, invalid):
    control = api().RuntimeControl(tmp_path / "runtime")
    with pytest.raises((TypeError, ValueError)):
        control.promote("v1", candidate(tmp_path, "v1"), None, expected_generation=invalid)
    assert control.snapshot()["generation"] == 0
    assert control.events() == []
