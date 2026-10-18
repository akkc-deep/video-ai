from pathlib import Path
import json
import shutil
import pytest
from unit.test_automated_storyboard import automatic_run


@pytest.fixture
def imported(automatic_run):
    from video_ai.runtime.manifest import hash_file,thaw
    parent,config,store,delegation=automatic_run
    from video_ai.runtime.paths import RuntimePaths,create_run
    run=create_run(RuntimePaths.from_config(config));(run/'logs/storyboard').mkdir(parents=True)
    shutil.copytree(parent/'audio',run/'audio');shutil.copy2(parent/'script.txt',run/'script.txt')
    path=run/'logs/storyboard/upstream-import.json'
    record=dict(schema_version=1,parent_run=str(parent),created_at='2026-10-04T18:00:00+08:00',reason='Test-only import receipt',
        parent_manifest=thaw(hash_file(parent/'manifest.json')),parent_timeline=thaw(hash_file(parent/'timeline.json')),
        parent_segments=thaw(hash_file(parent/'segments.json')),parent_voice_listening=thaw(hash_file(parent/'voice-listening.json')),
        copies=[dict(original=thaw(hash_file(p)),copy=thaw(hash_file(run/p.relative_to(parent)))) for p in (parent/'audio').rglob('*') if p.is_file()])
    path.write_text(json.dumps(record),encoding='utf-8')
    segments=json.loads((parent/'segments.json').read_text(encoding='utf-8'))
    segments['import_provenance_identity']=thaw(hash_file(path))
    acceptance=json.loads((parent/'voice-listening.json').read_text(encoding='utf-8'))
    for item in acceptance['audio']:item['pcm']['path']=str(run/Path(item['pcm']['path']).relative_to(parent))
    acceptance['inherited_acceptance_identity']=record['parent_voice_listening']
    (run/'voice-listening.json').write_text(json.dumps(acceptance),encoding='utf-8')
    return run,parent,segments


def test_import_requires_fresh_original_acceptance_and_exact_copies(imported):
    from video_ai.runtime.storyboard_checks import _verify_import
    run,parent,segments=imported
    _verify_import(run,segments)
    with (parent/'voice-listening.json').open('a') as output:output.write(' ')
    with pytest.raises((ValueError,OSError)):_verify_import(run,segments)


def test_import_rejects_copied_audio_drift(imported):
    from video_ai.runtime.storyboard_checks import _verify_import
    run,parent,segments=imported
    _verify_import(run,segments)
    (run/'audio/speech_0001/pcm-48000.wav').write_bytes(b'Different audio')
    with pytest.raises((ValueError,OSError)):_verify_import(run,segments)


@pytest.mark.parametrize('bad',['parent_segments','parent_timeline','parent_manifest','original_copy','import_document','inherited_binding','accepted_false','missing_copy'])
def test_import_drift_and_false_original_acceptance_are_rejected(imported,bad):
    from video_ai.runtime.storyboard_checks import _verify_import
    from video_ai.runtime.manifest import hash_file,thaw
    run,parent,segments=imported
    _verify_import(run,segments)
    document=run/'logs/storyboard/upstream-import.json'
    if bad.startswith('parent_'):
        with (parent/(bad.removeprefix('parent_')+'.json')).open('a') as output:output.write(' ')
    elif bad=='original_copy':(parent/'audio/speech_0001/pcm-48000.wav').write_bytes(b'Changed source')
    elif bad=='import_document':
        with document.open('a') as output:output.write(' ')
    elif bad=='inherited_binding':
        path=run/'voice-listening.json';data=json.loads(path.read_text(encoding='utf-8'))
        data['inherited_acceptance_identity']=thaw(hash_file(parent/'script.txt'))
        path.write_text(json.dumps(data),encoding='utf-8')
    else:
        record=json.loads(document.read_text(encoding='utf-8'))
        if bad=='accepted_false':
            path=parent/'voice-listening.json';data=json.loads(path.read_text(encoding='utf-8'));data['accepted']=False
            path.write_text(json.dumps(data),encoding='utf-8');record['parent_voice_listening']=thaw(hash_file(path))
            path=run/'voice-listening.json';data=json.loads(path.read_text(encoding='utf-8'))
            data['inherited_acceptance_identity']=record['parent_voice_listening'];path.write_text(json.dumps(data),encoding='utf-8')
        else:record['copies'].pop()
        document.write_text(json.dumps(record),encoding='utf-8');segments['import_provenance_identity']=thaw(hash_file(document))
    with pytest.raises((ValueError,OSError)):_verify_import(run,segments)


def test_import_is_rechecked_immediately_before_commit(imported,monkeypatch):
    from types import SimpleNamespace
    from video_ai.runtime import storyboard_checks as sc
    run,parent,segments=imported
    sc._verify_import(run,segments)
    (run/'segments.json').write_text(json.dumps(segments),encoding='utf-8')
    stages={'speech':{},'timeline':{},'storyboard':{'status':'running'}}
    store=SimpleNamespace(snapshot=lambda:{'stages':stages})
    monkeypatch.setattr(sc,'_check_lock',lambda *args:None)
    with (parent/'voice-listening.json').open('a') as output:output.write(' ')
    with pytest.raises((ValueError,OSError)):sc._unchanged(store,{'stages':stages},{},run,{})
