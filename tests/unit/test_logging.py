import json
import pytest


def test_logger_preserves_exclusive_evidence(runtime_run):
    from video_ai.runtime.logging import RunLogger
    run, _, _ = runtime_run
    log = RunLogger(run)
    path = log.save_bytes('http/response.bin', b'raw invalid \xff')
    assert path.read_bytes() == b'raw invalid \xff'
    with pytest.raises(FileExistsError):
        log.save_bytes('http/response.bin', b'overwrite')
    log.event('source_clips', 'shot_0001', 'response', {'path':str(path)})
    event = json.loads((run / 'logs/events.jsonl').read_text())
    assert event['unit_id'] == 'shot_0001'
    assert event['details']['path'] == str(path)
    try:
        raise RuntimeError('visible exception')
    except RuntimeError as exc:
        trace = log.exception('speech', None, exc)
    assert 'RuntimeError: visible exception' in trace.read_text()


@pytest.mark.parametrize('name', ['../escape','C:/escape','x/../../escape','x:bad','NUL','bad.'])
def test_logger_rejects_escape_before_write(runtime_run, name):
    from video_ai.runtime.logging import RunLogger
    log = RunLogger(runtime_run[0])
    with pytest.raises(ValueError):
        log.save_bytes(name, b'bad')
