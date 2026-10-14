"""Account ownership survives restarts, pool edits and hostile private inputs."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import importlib
import json
from pathlib import Path
import tempfile
import traceback
import pytest
try:
    pool_module = importlib.import_module('pdf_rules.mineru_account_pool')
except ModuleNotFoundError:
    pool_module = None

@pytest.fixture
def api():
    return pool_module

@pytest.fixture
def private_files(tmp_path):

    def make(keys, *, legacy=None, raw=None, mode=384):
        pool = tmp_path / 'private-pool.json'
        pool.write_text(raw if raw is not None else json.dumps({'format': 'mineru-private-key-pool-v1', 'keys': keys}), encoding='utf-8')
        pool.chmod(mode)
        old = tmp_path / 'legacy-token.txt'
        old.write_text((legacy if legacy is not None else keys[0]) + '\n', encoding='utf-8')
        old.chmod(384)
        return (pool, old)
    return make
TOKENS = ('fixture-account-alpha', 'fixture-account-beta', 'fixture-account-gamma')

def test_loaded_pool_deduplicates_keys_and_hides_tokens(api, private_files):
    assert api is not None, 'fixed-task account pool API is absent'
    path, legacy = private_files([TOKENS[0], TOKENS[1], TOKENS[0], TOKENS[2]])
    pool = api.load_account_pool(path, legacy_token_path=legacy)
    assert len(pool.accounts) == 3
    assert pool.legacy_account.account_id == sha256(TOKENS[0].encode()).hexdigest()
    assert pool.legacy_account.token == TOKENS[0]
    for token in TOKENS:
        assert token not in repr(pool)
        assert token not in repr(pool.accounts)
    assert json.dumps(pool.diagnostics()) == json.dumps({'account_count': 3, 'legacy_account_id': sha256(TOKENS[0].encode()).hexdigest()})

def test_new_pdf_assignment_is_reproducible_and_fair_for_static_load(api):
    assert api is not None, 'fixed-task account pool API is absent'
    first = api.MinerUAccountPool.from_tokens(TOKENS)
    reordered = api.MinerUAccountPool.from_tokens(reversed(TOKENS))
    identities = [sha256(f'static-pdf-load-{i:04}'.encode()).hexdigest() for i in range(600)]
    ids = [first.select_for_pdf(identity).account_id for identity in identities]
    assert ids == [reordered.select_for_pdf(identity).account_id for identity in identities]
    counts = Counter(ids)
    assert len(counts) == 3
    assert all((160 <= count <= 240 for count in counts.values())), counts

def test_account_removal_only_reassigns_pdfs_owned_by_removed_account(api):
    assert api is not None, 'fixed-task account pool API is absent'
    full = api.MinerUAccountPool.from_tokens(TOKENS)
    fewer = api.MinerUAccountPool.from_tokens(TOKENS[:2])
    removed = sha256(TOKENS[2].encode()).hexdigest()
    for i in range(100):
        identity = f'pdf-{i}'
        chosen = full.select_for_pdf(identity)
        if chosen.account_id != removed:
            assert fewer.select_for_pdf(identity).account_id == chosen.account_id

def test_fixed_binding_is_immutable_and_thread_independent(api):
    assert api is not None, 'fixed-task account pool API is absent'
    pool = api.MinerUAccountPool.from_tokens(TOKENS)
    with ThreadPoolExecutor(max_workers=32) as workers:
        bound = list(workers.map(lambda _: pool.bind_task('same-pdf'), range(64)))
    assert len({account.account_id for account in bound}) == 1
    owner = bound[0]
    with pytest.raises((AttributeError, TypeError)):
        owner.token = 'replacement'

def test_marked_pending_task_uses_exact_owner_after_pool_reorder(api, private_files):
    assert api is not None, 'fixed-task account pool API is absent'
    path, legacy = private_files(list(TOKENS))
    original = api.load_account_pool(path, legacy_token_path=legacy)
    selected = original.bind_task('pdf-to-resume')
    path.write_text(json.dumps({'format': 'mineru-private-key-pool-v1', 'keys': list(reversed(TOKENS))}))
    restarted = api.load_account_pool(path, legacy_token_path=legacy)
    resumed = restarted.bind_task('changed-selector-input', pending_owner_id=selected.account_id)
    assert resumed.token == selected.token
    assert resumed.account_id == selected.account_id

def test_pending_without_owner_pins_legacy_across_pool_reorder(api, private_files):
    assert api is not None, 'fixed-task account pool API is absent'
    path, legacy = private_files(list(reversed(TOKENS)), legacy=TOKENS[0])
    pool = api.load_account_pool(path, legacy_token_path=legacy)
    assert pool.bind_task('pdf', legacy_unmarked=True).token == TOKENS[0]
    assert pool.resolve_pending_owner(None).token == TOKENS[0]

def test_missing_pending_owner_fails_instead_of_polling_another_key(api):
    assert api is not None, 'fixed-task account pool API is absent'
    pool = api.MinerUAccountPool.from_tokens(TOKENS[:2])
    missing = sha256(TOKENS[2].encode()).hexdigest()
    with pytest.raises(api.MinerUAccountPoolError) as raised:
        pool.bind_task('pdf', pending_owner_id=missing)
    assert raised.value.reason_code == 'owner_missing'
    assert missing not in str(raised.value)

@pytest.mark.parametrize('owner', ['fixture-private-token-in-owner', '', 7, {}, 'a' * 65])
def test_hostile_owner_identity_never_leaks_in_errors(api, owner):
    assert api is not None, 'fixed-task account pool API is absent'
    pool = api.MinerUAccountPool.from_tokens(TOKENS)
    with pytest.raises(api.MinerUAccountPoolError) as raised:
        pool.resolve_pending_owner(owner)
    text = str(raised.value) + repr(raised.value) + json.dumps(raised.value.diagnostics)
    assert 'fixture-private-token-in-owner' not in text
    assert raised.value.reason_code == 'owner_invalid'

def test_completed_layout_cache_can_be_reused_without_pending_account(api, tmp_path):
    assert api is not None, 'fixed-task account pool API is absent'
    from pdf_rules.mineru_cache import RawLayoutCache
    pool = api.MinerUAccountPool.from_tokens(TOKENS)
    cache = RawLayoutCache(tmp_path / 'cache')
    key = cache.key(b'exact-uploaded-pdf-bytes')
    pages = [{'page_idx': 0, 'preproc_blocks': []}]
    assert cache.write(key, pages)
    for account in pool.accounts:
        assert cache.read(key, 1) == pages
    assert pool.resolve_pending_owner(pool.accounts[1].account_id).token == TOKENS[1]

@pytest.mark.parametrize('record', [{'format': 'unknown', 'keys': list(TOKENS)}, {'format': 'mineru-private-key-pool-v1', 'keys': []}, {'format': 'mineru-private-key-pool-v1', 'keys': 'fixture-secret'}, {'format': 'mineru-private-key-pool-v1', 'keys': [1]}, {'format': 'mineru-private-key-pool-v1', 'keys': ['']}, {'format': 'mineru-private-key-pool-v1', 'keys': ['fixture-secret\ninjected']}, {'format': 'mineru-private-key-pool-v1', 'keys': ['fixture-secret'], 'unexpected': 'private'}, ['fixture-secret'], None])
def test_bad_private_schema_fails_safely(api, tmp_path, record):
    assert api is not None, 'fixed-task account pool API is absent'
    path = tmp_path / 'fixture-secret-filename'
    path.write_text(json.dumps(record))
    path.chmod(384)
    with pytest.raises(api.MinerUAccountPoolError) as raised:
        api.load_account_pool(path)
    text = ''.join(traceback.format_exception(raised.value))
    assert 'fixture-secret' not in text
    assert raised.value.reason_code == 'pool_invalid'

@pytest.mark.parametrize('raw', ['{broken-private-secret', '{"format":"mineru-private-key-pool-v1","keys":["a"],"keys":["fixture-secret"]}'])
def test_malformed_json_and_duplicate_fields_are_rejected_without_echo(api, tmp_path, raw):
    assert api is not None, 'fixed-task account pool API is absent'
    path = tmp_path / 'private.json'
    path.write_text(raw)
    path.chmod(384)
    with pytest.raises(api.MinerUAccountPoolError) as raised:
        api.load_account_pool(path)
    assert 'private-secret' not in ''.join(traceback.format_exception(raised.value))
    assert 'fixture-secret' not in ''.join(traceback.format_exception(raised.value))

def test_unreadable_missing_path_and_directory_are_safe(api, tmp_path):
    assert api is not None, 'fixed-task account pool API is absent'
    for path in [tmp_path / 'fixture-secret-missing', tmp_path]:
        with pytest.raises(api.MinerUAccountPoolError) as raised:
            api.load_account_pool(path)
        assert 'fixture-secret' not in ''.join(traceback.format_exception(raised.value))
        assert raised.value.reason_code == 'pool_unavailable'

def test_symlink_and_world_readable_secret_files_are_rejected(api, private_files, tmp_path):
    assert api is not None, 'fixed-task account pool API is absent'
    path, legacy = private_files(list(TOKENS), mode=420)
    with pytest.raises(api.MinerUAccountPoolError) as raised:
        api.load_account_pool(path)
    assert raised.value.reason_code == 'pool_permissions'
    path.chmod(384)
    link = tmp_path / 'link.json'
    link.symlink_to(path)
    with pytest.raises(api.MinerUAccountPoolError):
        api.load_account_pool(link)

def test_oversized_and_invalid_utf8_files_do_not_escape_secret_bytes(api, tmp_path):
    assert api is not None, 'fixed-task account pool API is absent'
    for content in [b'x' * (256 * 1024 + 1), b'fixture-secret\xff']:
        path = tmp_path / 'secret.json'
        path.write_bytes(content)
        path.chmod(384)
        with pytest.raises(api.MinerUAccountPoolError) as raised:
            api.load_account_pool(path)
        assert 'fixture-secret' not in ''.join(traceback.format_exception(raised.value))

def test_legacy_only_factory_preserves_single_key_and_strips_terminal_newline(api, tmp_path):
    assert api is not None, 'fixed-task account pool API is absent'
    path = tmp_path / 'legacy.txt'
    path.write_text(TOKENS[0] + '\n')
    path.chmod(384)
    pool = api.load_account_pool(None, legacy_token_path=path)
    assert len(pool.accounts) == 1
    assert pool.bind_task('anything').token == TOKENS[0]

def test_configured_legacy_missing_from_pool_fails_instead_of_guessing(api, private_files):
    assert api is not None, 'fixed-task account pool API is absent'
    path, legacy = private_files(list(TOKENS[:2]), legacy=TOKENS[2])
    with pytest.raises(api.MinerUAccountPoolError) as raised:
        api.load_account_pool(path, legacy_token_path=legacy)
    assert raised.value.reason_code == 'legacy_missing'
    assert TOKENS[2] not in str(raised.value)

@pytest.mark.parametrize('identity', ['', None, {}, b'', 'fixture-secret\n'])
def test_bad_pdf_identity_uses_sanitized_error(api, identity):
    assert api is not None, 'fixed-task account pool API is absent'
    pool = api.MinerUAccountPool.from_tokens(TOKENS)
    with pytest.raises(api.MinerUAccountPoolError) as raised:
        pool.select_for_pdf(identity)
    assert raised.value.reason_code == 'pdf_identity_invalid'
    assert 'fixture-secret' not in str(raised.value)

def test_hostile_path_exception_is_sanitized(api):
    class HostilePath:
        def __fspath__(self):
            raise RuntimeError("fixture-secret-path-failure")
    with pytest.raises(api.MinerUAccountPoolError) as raised:
        api.load_account_pool(HostilePath())
    assert raised.value.reason_code == "pool_unavailable"
    assert "fixture-secret" not in "".join(traceback.format_exception(raised.value))


def test_hostile_token_iterator_exception_is_sanitized(api):
    class HostileTokens:
        def __iter__(self):
            raise OSError("fixture-secret-iterator-failure")
    with pytest.raises(api.MinerUAccountPoolError) as raised:
        api.MinerUAccountPool.from_tokens(HostileTokens())
    assert "fixture-secret" not in "".join(traceback.format_exception(raised.value))


def test_pdf_identity_invalid_unicode_is_sanitized(api):
    identity = "fixture-secret-" + chr(0xD800)
    with pytest.raises(api.MinerUAccountPoolError) as raised:
        api.MinerUAccountPool.from_tokens(TOKENS).select_for_pdf(identity)
    assert raised.value.reason_code == "pdf_identity_invalid"
    assert "fixture-secret" not in "".join(traceback.format_exception(raised.value))


def test_json_bom_is_rejected_safely(api, tmp_path):
    path = tmp_path / "pool.json"
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps({
        "format": "mineru-private-key-pool-v1", "keys": list(TOKENS)}).encode())
    path.chmod(0o600)
    with pytest.raises(api.MinerUAccountPoolError):
        api.load_account_pool(path)

@pytest.mark.parametrize("failure", ["json", "utf8", "path", "iterator", "iteration", "unicode"])
def test_private_failure_does_not_retain_secret_exception_context(api, tmp_path, failure):
    marker = "fixture-retained-secret"
    path = tmp_path / "pool.json"
    class BadPath:
        def __fspath__(self):
            raise OSError(marker)
    class BadIterator:
        def __iter__(self):
            raise OSError(marker)
    class BadIteration:
        def __iter__(self):
            yield TOKENS[0]
            raise RuntimeError(marker)
    if failure == "json":
        path.write_text("{" + marker); path.chmod(0o600)
        operation = lambda: api.load_account_pool(path)
    elif failure == "utf8":
        path.write_bytes(marker.encode() + b"\xff"); path.chmod(0o600)
        operation = lambda: api.load_account_pool(path)
    elif failure == "path":
        operation = lambda: api.load_account_pool(BadPath())
    elif failure == "iterator":
        operation = lambda: api.MinerUAccountPool.from_tokens(BadIterator())
    elif failure == "iteration":
        operation = lambda: api.MinerUAccountPool.from_tokens(BadIteration())
    else:
        identity = marker + chr(0xD800)
        operation = lambda: api.MinerUAccountPool.from_tokens(TOKENS).select_for_pdf(identity)
    with pytest.raises(api.MinerUAccountPoolError) as raised:
        operation()
    assert raised.value.__context__ is None, "private original exception retained"
    assert marker not in str(raised.value)
    assert marker not in repr(raised.value)
