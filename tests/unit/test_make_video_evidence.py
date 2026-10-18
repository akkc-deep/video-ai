"""Guard the development audit against self-consistent source substitution."""
import importlib.util
from copy import deepcopy

import pytest


@pytest.fixture
def audit():
    spec = importlib.util.spec_from_file_location('make06_audit', 'D:/VideoSi/docs/video-ai/make-video-evidence/verify_make06.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('change', ['none', 'swapped_pcm', 'moved_sample', 'wrong_unit'])
def test_audit_narration_is_bound_to_original_timeline(audit, change):
    rows = [dict(unit_id='speech_0001', start_sample=0, end_sample=2, samples=2, pcm={'path': 'one.wav'}),
            dict(unit_id='speech_0002', start_sample=4, end_sample=6, samples=2, pcm={'path': 'two.wav'})]
    timeline = dict(clips=[dict(row, pcm=dict(stamp=row['pcm'])) for row in rows])
    speech = dict(spans=[dict(unit_id=row['unit_id'], pcm=row['pcm'], samples=2, kind='speech') for row in rows])
    narration = dict(clips=deepcopy(rows))
    if change == 'swapped_pcm':
        narration['clips'][0]['pcm'], narration['clips'][1]['pcm'] = narration['clips'][1]['pcm'], narration['clips'][0]['pcm']
    elif change == 'moved_sample':
        narration['clips'][0]['start_sample'] = 1
    elif change == 'wrong_unit':
        narration['clips'][0]['unit_id'] = 'speech_0002'
    if change == 'none':
        audit.validate_narration_sources(timeline, speech, narration)
    else:
        with pytest.raises(AssertionError):
            audit.validate_narration_sources(timeline, speech, narration)


@pytest.mark.parametrize('change', ['none', 'swapped_frame', 'wrong_index'])
def test_audit_contributions_are_bound_to_original_upscale_frames(audit, change):
    upscale = dict(clips=[dict(shot_id='shot_0001', frames=[dict(output={'path': 'one.png'}), dict(output={'path': 'two.png'})])])
    rows = [dict(output_frame_index=i, shot_id='shot_0001', source_frame_index=i, upscaled_frame_index=i,
                 input={'path': path}, output={'path': f'target-{i}.png'}) for i, path in enumerate(('one.png', 'two.png'))]
    if change == 'swapped_frame':
        rows[0]['input'], rows[1]['input'] = rows[1]['input'], rows[0]['input']
    elif change == 'wrong_index':
        rows[0]['source_frame_index'] = 1
    if change == 'none':
        audit.validate_contributions(upscale, rows)
    else:
        with pytest.raises(AssertionError):
            audit.validate_contributions(upscale, rows)


@pytest.mark.parametrize('change', ['none', 'client', 'graph', 'unit', 'evidence'])
def test_audit_posts_require_original_intent_and_checkpoint_identity(audit, change):
    graph = {'3': {'class_type': 'ImageUpscaleWithModel', 'inputs': {'image': 'original.png'}}}
    rows = [dict(path='request-1', request=dict(stage='start_images', unit_id='shot_0001',
                 json_body=dict(prompt=deepcopy(graph), client_id='original-client')))]
    records = {('start_images', 'shot_0001'): dict(intent=graph, request=dict(client_id='original-client', response_paths=['request-1']))}
    if change == 'client': rows[0]['request']['json_body']['client_id'] = 'foreign'
    elif change == 'graph': rows[0]['request']['json_body']['prompt']['3']['inputs']['image'] = 'foreign.png'
    elif change == 'unit': rows[0]['request']['unit_id'] = 'shot_0002'
    elif change == 'evidence': rows[0]['path'] = 'foreign-request'
    if change == 'none':
        audit.validate_post_intents(rows, records)
    else:
        with pytest.raises(AssertionError):
            audit.validate_post_intents(rows, records)
