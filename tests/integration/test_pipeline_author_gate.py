"""TEST ONLY supplied acceptance must have its matching author review."""
import json
import pytest
from pipeline_helpers import patch_committed_upstream, review_index, write


@pytest.mark.parametrize('stale', [False, True])
def test_standalone_supplied_acceptance_refuses_before_default_resume(runtime_run, monkeypatch, stale):
    from publication_helpers import make_publication_fixture, cleanup_output
    from video_ai.pipeline import resume_pipeline
    run, config, store, review, acceptance = make_publication_fixture(runtime_run, monkeypatch)
    composition = json.loads((run/'composition.json').read_text(encoding='utf-8'))
    patch_committed_upstream(monkeypatch, composition)
    if stale:
        data = json.loads(acceptance.read_text(encoding='utf-8'))
        data['candidate_identity']['sha256'] = 'a'*64
        write(acceptance, data)
    index = review_index(run, {'full_film_acceptance': acceptance})
    before = (run/'manifest.json').read_bytes()
    try:
        with pytest.raises(ValueError, match='supplied acceptance requires matching final_review'):
            resume_pipeline(config, run_dir=run, reviews_path=index)
        assert (run/'manifest.json').read_bytes() == before
        assert store.snapshot()['stages']['publish']['status'] == 'pending'
        assert not (config.output_root/(run.name+'.mp4')).exists()
    finally:
        cleanup_output(config, run)
