import importlib.util
from pathlib import Path
import pytest


def recorder():
    path = Path('D:/VideoSi/docs/video-ai/VAI-14-evidence/cli_result_recording.py')
    assert path.is_file(), 'native CLI result validation is missing'
    spec = importlib.util.spec_from_file_location('cli_result_recording', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('stdout', ['', '{invalid', '[]', '{}', '{"status":"review_required"}'])
def test_bad_stdout_preserves_native_code_and_original_stderr(stdout):
    module = recorder()
    parsed = module.parse_result(stdout)
    with pytest.raises(RuntimeError) as error:
        module.require_result(1, parsed, expected_code=1, status='review_required', clip_count=15,
                              stdout=stdout, stderr='original mapping closure refusal')
    assert 'exit_code=1' in str(error.value)
    assert 'original mapping closure refusal' in str(error.value)
    assert repr(stdout) in str(error.value)


def test_nonzero_native_exit_never_becomes_success():
    module = recorder()
    with pytest.raises(RuntimeError, match='exit_code=2'):
        module.require_result(2, {'status':'completed', 'clip_count':15}, expected_code=0,
                              status='completed', clip_count=15, stdout='{}', stderr='refused')


def test_real_review_required_contract_keeps_native_exit_one():
    module = recorder()
    result = module.parse_result('{"status":"review_required","clip_count":15}')
    module.require_result(1, result, expected_code=1, status='review_required', clip_count=15,
                          stdout='', stderr='')


def test_actual_phase_recorder_reports_first_failure(tmp_path,monkeypatch):
    import sys
    root = Path('D:/VideoSi/docs/video-ai/VAI-14-evidence')
    monkeypatch.syspath_prepend(str(root))
    spec = importlib.util.spec_from_file_location('source_to_upscale_recorder',root/'continue_confirmed_source_to_upscale_v1.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    monkeypatch.setattr(module,'E',tmp_path)
    stem = tmp_path/'confirmed-source-to-upscale-v1-prepare-upscale'
    Path(str(stem)+'-stdout.log').write_bytes(b'')
    Path(str(stem)+'-stderr.log').write_text('original mapping closure refusal',encoding='utf-8')
    with pytest.raises(RuntimeError,match='original mapping closure refusal'):
        module.require_phase_result('prepare-upscale',1,{'parse_error':True},expected_code=1,status='review_required')
