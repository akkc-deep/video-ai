"""Authentic upstream admission and real, offline candidate media composition."""
from pathlib import Path
import json
import wave
import pytest

from video_ai.runtime.production_scene_composition import produce_scene_composition
from video_ai.runtime.scene_media_records import require_scene_composition


def compose(setup, **kwargs):
    return produce_scene_composition(setup['frozen'], setup['units'], setup['timeline'],
        paths=setup['paths'], logger=setup['logger'], **kwargs)


def test_candidate_preserves_original_pcm_subtitles_and_awaits_actual_review(runtime_run, tmp_path, monkeypatch):
    from scene_media_helpers import prepared_upscaled
    from video_ai.media.subtitles import srt_text, ass_text
    from video_ai.planning.composition import CompositionSettings
    original_write=wave.Wave_write.writeframes
    def original_speech(writer,data):
        path=Path(str(getattr(writer._file,'name','')))
        if path.name=='pcm.wav':
            sample=1+sum(path.parent.name.encode('utf-8'))%200
            data=bytes((sample,0))*(len(data)//2)
        return original_write(writer,data)
    # Author nonzero original speech before authentic timeline/image/clip admission.
    monkeypatch.setattr(wave.Wave_write,'writeframes',original_speech)
    setup = prepared_upscaled(runtime_run, tmp_path, monkeypatch)
    monkeypatch.setattr(wave.Wave_write,'writeframes',original_write)
    result = compose(setup)
    assert result.status == 'awaiting_final_review', result.error
    assert result.exit_code == 3
    root = setup['run'] / 'production/scene-composition'
    candidate = require_scene_composition(setup['frozen'], setup['units'], setup['timeline'])
    assert Path(result.candidate) == root/'candidate.mp4'
    assert Path(result.candidate).is_file()
    materialized = json.loads((root/'materialized.json').read_text(encoding='utf-8'))
    settings = CompositionSettings()
    assert Path(materialized['subtitle']['path']).read_bytes() == srt_text(materialized['subtitle_events']).encode()
    assert Path(materialized['ass']['path']).read_bytes() == ass_text(materialized['subtitle_events'], settings).encode()
    timeline = setup['timeline']
    with wave.open(materialized['narration']['audio']['path'], 'rb') as audio:
        assert audio.getnframes() == timeline.total_frames*3000
        actual = audio.readframes(audio.getnframes())
    cursor = 0
    for clip in timeline.clips:
        assert actual[cursor*2:clip.start_sample*2] == bytes((clip.start_sample-cursor)*2)
        with wave.open(str(clip.pcm.path), 'rb') as source:
            expected=source.readframes(clip.samples)
            assert any(expected)
            assert actual[clip.start_sample*2:clip.end_sample*2] == expected
        cursor = clip.end_sample
    assert actual[cursor*2:] == bytes((timeline.total_frames*3000-cursor)*2)
    assert timeline.video_padding_samples > 0
    assert all(value == 'passed' for value in candidate['technical_checks'].values())
    template = json.loads(Path(result.final_observation_template).read_text(encoding='utf-8'))
    assert template['verdict'] == 'unverified'
    for path in setup['frozen'].options['output_paths'].values():
        assert not Path(path).exists()


def test_missing_scene_observation_prevents_any_composition_encode(runtime_run,tmp_path,monkeypatch):
    from scene_clip_helpers import prepared_wan
    import video_ai.runtime.production_scene_composition as module
    setup=prepared_wan(runtime_run,tmp_path,monkeypatch)
    monkeypatch.setattr(module,'run_logged',lambda *a,**k:pytest.fail('unadmitted scenes cannot encode'))
    result=compose(setup)
    assert result.status=='blocked',result.error
    assert not (setup['run']/'production/scene-composition').exists()


def test_unknown_run_refuses_before_assigning_identity_or_writing(runtime_run):
    from types import SimpleNamespace
    run,config,paths=runtime_run
    unknown=run.parent/('unknown-'+run.name)
    frozen=SimpleNamespace(options=dict(script_path=str(unknown/'production/script.txt'),run_id=unknown.name),config=config)
    logger=SimpleNamespace(run_dir=run,production=True,root=run/'logs/production')
    result=produce_scene_composition(frozen,{},None,paths=paths,logger=logger)
    assert result.status=='blocked'
    assert result.run_id is None and result.run_dir is None and result.log_dir is None
    assert not unknown.exists()

