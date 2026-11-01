"""Fixture-only whole mode: genuine CPU media, no model or viewing claim."""
from copy import deepcopy
import json
from pathlib import Path
from uuid import uuid4

import pytest
from video_ai.runtime.scene_revision_records import revision_validation,revision_scope

from integration.test_scene_revision_flow import revision_source, revision_request, tree_identity


def whole_revision(setup, tmp_path, monkeypatch, *, font_file=None):
    from unit.test_scene_execution_records import fixture_evidence
    from unit.test_scene_video_prompts import contract_for, reviewed
    from video_ai.planning.scene_execution import derive_scene_execution_clips
    from video_ai.planning.production_scenes import canonical_digest
    from video_ai.runtime.manifest import thaw
    from video_ai.runtime.reference_image_records import require_reference_image_acceptance
    from video_ai.runtime.production_scene_revision import create_scene_revision
    from video_ai.runtime import scene_execution_records
    evidence = fixture_evidence(setup['run'].parent/('whole-fixture-evidence-'+uuid4().hex),monkeypatch)
    # Synthetic test resources are deliberately distinct from real Wan models.
    # The evidence validator itself remains real and checks all fixture bytes.
    monkeypatch.setattr(scene_execution_records,'verify_current_environment',lambda *a,**k:None)
    f,b,p,t = setup['frozen'],setup['bible'],setup['plan'],setup['timeline']
    wan = require_reference_image_acceptance(f,setup['units'],t)
    clips=derive_scene_execution_clips(p,t,mode='whole_scene_v1')
    contract=contract_for(b,p,wan)
    by_id={c['clip_id']:c for c in contract['clips']}
    contract.update(schema_version=2,clips=[by_id[c['clip_id']] for c in clips])
    contract['binding'].update(rendering_mode='whole_scene_v1',execution_clips_sha256=canonical_digest(clips))
    reviewed(contract)
    prompt=tmp_path/'whole-prompts.json'; prompt.write_text(json.dumps(contract,ensure_ascii=False),encoding='utf-8')
    raw=thaw(f.options['config_snapshot']['raw'])
    raw['scene_continuity']=dict(schema_version=1,policy='advisory_v1')
    if font_file is not None: raw['media']['font_file']=str(font_file)
    raw['scene_rendering']=dict(mode='whole_scene_v1',prompt_policy='visual_v2',prompt_contract=str(prompt),whole_scene_evidence=str(evidence))
    config=tmp_path/'whole-config.json'; config.write_text(json.dumps(raw,ensure_ascii=False),encoding='utf-8')
    path,request=revision_request(setup)
    request.update(kind='reconfigure',scene_ids=[],choices=[],config_path=str(config))
    path.write_text(json.dumps(request),encoding='utf-8')
    return create_scene_revision(setup['run'],path),request


@revision_validation
def whole_setup(revision_source,tmp_path,monkeypatch):
    from video_ai.runtime.production_inputs import load_frozen_inputs
    from video_ai.runtime.scene_revision_records import load_scene_common_prefix
    from video_ai.runtime.image_selection_records import load_committed_plan
    from video_ai.runtime.paths import RuntimePaths
    from video_ai.runtime.logging import RunLogger
    before=tree_identity(revision_source['run'])
    result,request=whole_revision(revision_source,tmp_path,monkeypatch)
    assert result.status=='revision_ready',result.error
    assert tree_identity(revision_source['run'])==before
    f=load_frozen_inputs(result.run_dir)
    units,timeline=load_scene_common_prefix(f)
    bible,plan=load_committed_plan(f,units,timeline)
    from video_ai.runtime.reference_image_records import build_reference_image_acceptance,require_reference_image_acceptance
    from video_ai.runtime.production_state import RunLock
    from video_ai.runtime._scene_revision_copy import RevisionStore
    # Materialize the same derived selection view as the production coordinator
    # before standalone source/media writers are exercised by the fixtures.
    with RunLock(result.run_dir) as held:
        expected=build_reference_image_acceptance(f,units,timeline)
        RevisionStore(result.run_dir,held).save(result.run_dir/'production/reference-images/wan-inputs.json',expected)
    require_reference_image_acceptance(f,units,timeline)
    return dict(run=result.run_dir,frozen=f,units=units,timeline=timeline,bible=bible,plan=plan,
        config=f.config,paths=RuntimePaths.from_config(f.config),logger=RunLogger(result.run_dir,production=True))


def offline_whole_backend(setup):
    from scene_clip_helpers import OfflineWan
    from video_ai.runtime.scene_execution_records import load_scene_execution
    execution=load_scene_execution(setup['frozen'],setup['plan'],setup['timeline'])
    # Only the offline service output inventory sees execution clips; the real
    # semantic setup stays untouched for every production reader.
    backend_setup=dict(setup,plan=dict(setup['plan'],clips=execution['clips']))
    return OfflineWan(backend_setup)


def test_whole_revision_has_separate_budget_and_current_observation_gate(revision_source,tmp_path,monkeypatch):
    from scene_clip_helpers import generate,observation
    from video_ai.runtime.scene_clip_records import scene_context,require_scene_clip_acceptance
    from video_ai.runtime.scene_execution_records import load_scene_execution
    setup=whole_setup(revision_source,tmp_path,monkeypatch)
    execution=load_scene_execution(setup['frozen'],setup['plan'],setup['timeline'])
    assert len(execution['clips'])==len(setup['plan']['scenes'])<len(setup['plan']['clips'])
    with revision_scope():
        context=scene_context(setup['frozen'],setup['units'],setup['timeline'])
    assert context['plan']==setup['plan']
    assert context['inputs']['schema_version']==3
    assert context['inputs']['algorithm']=='scene_wan_execution_v1'
    assert context['inputs']['execution_budget']['path']==str(setup['run']/'production/scene-rendering/execution-budget.json')
    assert all(r['budget']['parent_clip_id'] is None for r in context['rows'])
    backend=offline_whole_backend(setup)
    first=generate(setup,backend)
    assert first.status=='awaiting_continuity_review',first.error
    assert len(backend.posts)==len(execution['clips'])
    for template in first.observation_templates: observation(setup,template)
    with pytest.raises(ValueError),revision_scope():
        require_scene_clip_acceptance(setup['frozen'],setup['units'],setup['timeline'])
    complete=setup['run']/'production/scene-clips/complete.json'
    if complete.exists():
        assert json.loads(complete.read_text(encoding='utf-8'))['schema_version']==3
    assert len(backend.posts)==len(execution['clips'])


def test_whole_native_320_mapping_uses_real_decoded_media(runtime_run):
    from types import SimpleNamespace
    from video_ai.planning.scene_execution import derive_scene_execution_clips
    from video_ai.planning.scene_clip_continuation import scene_clip_frame_mapping
    from video_ai.runtime.processes import run_logged
    from video_ai.runtime.environment import build_child_env
    from video_ai.runtime.logging import RunLogger
    from video_ai.media.video import trim_scene_video,inspect_video
    from video_ai.config import load_config
    run,base,paths=runtime_run
    config=load_config(Path('D:/VideoSi/projects/video-ai/config/production.json'))
    source=run/'whole-fixture-native321.mp4'; logger=RunLogger(run,production=True)
    command=run_logged(tuple(map(str,[config.tools['ffmpeg'],'-nostdin','-n','-v','error','-f','lavfi',
        '-i','testsrc2=size=64x36:rate=16','-frames:v','321','-c:v','libx264','-pix_fmt','yuv420p',source])),
        cwd=run,env=build_child_env(paths),timeout=60,logger=logger,stage='fixture_only',unit_id='native321')
    assert command.returncode==0
    plan=dict(total_frames=320,scenes=[dict(scene_id='scene_0001',start_frame=0,end_frame=320)])
    budget=derive_scene_execution_clips(plan,SimpleNamespace(total_frames=320),mode='whole_scene_v1')[0]
    mapping=scene_clip_frame_mapping(budget,actual_generated_frames=321)
    assert mapping['retained_to_generated']==list(range(320))
    assert mapping['generated_to_retained'][-1] is None
    target=run/'whole-fixture-retained320.mp4'
    source_info,_=inspect_video(source,width=64,height=36,config=config,paths=paths,logger=logger,stage='fixture_only',unit_id='probe321')
    result,_=trim_scene_video(source,target,source_info=source_info,start_frame=0,end_frame=320,width=64,height=36,
        config=config,paths=paths,logger=logger,unit_id='retained320')
    assert result['frames']==320 and result['duration']==20


def test_whole_protocol_to_upscale_full_pcm_final_review_and_idempotent_delivery(revision_source,tmp_path,monkeypatch):
    """Real CPU bytes; fixed fixture admission isolates downstream transactions."""
    import wave
    from scene_clip_helpers import generate,admit_all
    from scene_media_helpers import OfflineUpscale
    from scene_pipeline_helpers import write_final_observation
    from video_ai.runtime import scene_execution_records as execution_records
    from video_ai.runtime.production_scene_upscale import produce_scene_upscaled_clips
    from video_ai.runtime.production_scene_composition import produce_scene_composition
    from video_ai.runtime.production_scene_delivery import consume_scene_final_observation,produce_scene_delivery
    from video_ai.runtime.scene_clip_records import require_scene_clip_acceptance
    from video_ai.runtime.scene_media_records import require_scene_delivery
    from video_ai.media.subtitles import srt_text
    setup=whole_setup(revision_source,tmp_path,monkeypatch)
    evidence=execution_records.verify_whole_scene_frozen(setup['frozen'])
    # Admission drift and the real current-diagnostic gate are exercised by the
    # preceding case and records tests. Freeze those fixture seams here to focus
    # on media/PCM/observation/delivery transactions without model or SMTP work.
    monkeypatch.setattr(execution_records,'verify_whole_scene_frozen',lambda *a,**k:evidence)
    monkeypatch.setattr('video_ai.runtime.scene_continuity_records.require_scene_continuity_acceptance',
        lambda *a,**k:{'ready':True,'fixture_only':True})
    def forbidden(*a,**k): raise AssertionError('fixture_only flow must not use network or SMTP')
    monkeypatch.setattr('socket.socket.connect',forbidden)
    monkeypatch.setattr('smtplib.SMTP',forbidden)
    wan=offline_whole_backend(setup)
    ready=admit_all(setup,wan)
    assert ready.status=='source_clips_ready',ready.error
    with revision_scope():
        complete=require_scene_clip_acceptance(setup['frozen'],setup['units'],setup['timeline'])
    assert complete['schema_version']==3
    assert len(complete['clips'])==len(setup['plan']['scenes'])
    assert [m['output_frame'] for c in complete['clips'] for m in c['frame_mapping']['output_to_generated']]==list(range(setup['timeline'].total_frames))
    upscaler=OfflineUpscale(setup)
    kwargs=dict(paths=setup['paths'],logger=setup['logger'])
    upscaled=produce_scene_upscaled_clips(setup['frozen'],setup['units'],setup['timeline'],**kwargs,**upscaler.kwargs)
    assert upscaled.status=='upscale_ready',upscaled.error
    assert len(upscaler.posts)==setup['timeline'].total_frames
    candidate=produce_scene_composition(setup['frozen'],setup['units'],setup['timeline'],**kwargs)
    assert candidate.status=='awaiting_final_review',candidate.error
    materialized=json.loads((setup['run']/'production/scene-composition/materialized.json').read_text(encoding='utf-8'))
    assert Path(materialized['subtitle']['path']).read_bytes()==srt_text(materialized['subtitle_events']).encode('utf-8')
    with wave.open(materialized['narration']['audio']['path'],'rb') as audio:
        actual=audio.readframes(audio.getnframes())
        assert audio.getnframes()==setup['timeline'].total_frames*3000
    for clip in setup['timeline'].clips:
        with wave.open(str(clip.pcm.path),'rb') as pcm:
            assert actual[clip.start_sample*2:clip.end_sample*2]==pcm.readframes(clip.samples)
    for path in setup['frozen'].options['output_paths'].values(): assert not Path(path).exists()
    waiting=produce_scene_delivery(setup['frozen'],setup['units'],setup['timeline'],**kwargs)
    assert waiting.status=='blocked',waiting.error
    assert waiting.error['kind']=='ProductionRefused'
    assert all(not Path(path).exists() for path in setup['frozen'].options['output_paths'].values())
    authored=write_final_observation(setup,candidate.final_observation_template)
    final=consume_scene_final_observation(setup['frozen'],setup['units'],setup['timeline'],authored,**kwargs)
    assert final.status=='final_review_ready',final.error
    published=produce_scene_delivery(setup['frozen'],setup['units'],setup['timeline'],**kwargs)
    assert published.status=='delivered',published.error
    with revision_scope():
        receipt=require_scene_delivery(setup['frozen'],setup['units'],setup['timeline'])
    before=tree_identity(setup['run']);posts=(len(wan.posts),len(upscaler.posts))
    assert generate(setup,wan).status=='source_clips_ready'
    assert produce_scene_delivery(setup['frozen'],setup['units'],setup['timeline'],**kwargs).status=='delivered'
    with revision_scope():
        assert require_scene_delivery(setup['frozen'],setup['units'],setup['timeline'])==receipt
    assert (len(wan.posts),len(upscaler.posts))==posts
    assert tree_identity(setup['run'])==before
