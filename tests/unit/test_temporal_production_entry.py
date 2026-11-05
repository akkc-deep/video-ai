"""Fresh native preflight uses active roles, keeping legacy checks intact."""
from dataclasses import replace
import json
from pathlib import Path
import subprocess

from unit.test_production_inputs import production_config


def native_config(config):
    return replace(config,production_strategy='paragraph_jimeng_v1',
        raw=dict(scene_rendering=dict(mode='temporal_extension_v1')),
        workflows=dict(upscale=config.workflows['upscale']),models=dict(upscale=config.models['upscale']))


def test_native_local_preflight_has_only_upscale_without_wan_assets(resource_config,capability_runner):
    from video_ai.runtime.preflight import preflight
    report=preflight(native_config(resource_config),runner=capability_runner,automatic=True)
    assert report.passed,report.as_dict()
    assert [c.name for c in report.checks if c.name.startswith('workflow.')]==['workflow.upscale']
    assert not any(c.name.startswith('models.wan') for c in report.checks)


def test_native_model_paths_validate_only_the_enabled_comfy_role(runtime_run):
    from video_ai.runtime.production_visual_templates import validate_production_model_paths
    validate_production_model_paths(native_config(runtime_run[1]))


def test_fresh_native_production_preflight_with_frozen_upscale_only(production_config,runtime_run):
    from video_ai.runtime.production_inputs import production_preflight
    run,original,_=runtime_run
    config=native_config(replace(production_config,models=original.models))
    def runner(args,**kwargs):
        assert Path(kwargs['cwd']).is_relative_to(run)
        if args[-1]=='-encoders':text=' V....D libx264 H264\n A..... aac AAC\n'
        elif args[-1]=='-filters':text=' .. subtitles V->V render\n'
        elif '-c' in args:text=json.dumps({'custom':{'version':'v2','device':'cpu','is_half':False}})
        else:text='fixture_only capability version\n'
        kwargs['stdout'].write(text)
        return subprocess.CompletedProcess(args,0)
    report=production_preflight(config,run,runner=runner,port_probe=lambda *a:False)
    assert report.passed,report.as_dict()
    assert any(c.name=='workflow.upscale' and c.passed for c in report.checks)
    assert not any(c.name=='workflow.wan' for c in report.checks)


def test_coordinator_restores_native_schema4_bound_by_later_upscale(runtime_run,monkeypatch):
    from types import SimpleNamespace
    from unit.test_temporal_chain_records import chain_fixture,write_chain
    from unit.test_temporal_scene_records import put
    from unit.test_temporal_scene_observations import author,NOW
    from video_ai.planning.production_scenes import canonical_digest
    from video_ai.runtime.temporal_scene_observations import build_temporal_observation_template
    from video_ai.runtime.production_state import RunLock
    from video_ai.runtime import production_scene_pipeline as pipeline,scene_clip_records
    records,context,row,window=chain_fixture(runtime_run,monkeypatch)
    context['execution']=dict(mode='temporal_extension_v1');context['units']=[]
    folder,raw,result_id=write_chain(context,window)
    chain=records.validate_temporal_chain(context,'scene_0001',[window])
    template=build_temporal_observation_template(context,chain,scope='scene_temporal_chain_process')
    observation=put(folder/'observations/full.json',author(template))
    put(folder/'accepted.json',dict(schema_version=1,algorithm='temporal_chain_acceptance_v1',
        result_sha256=result_id['sha256'],template_sha256=canonical_digest(template),observation=observation,
        verdict='passed',accepted_at=NOW.isoformat()))
    progress=records.collect_temporal_progress(context)
    expected=records.complete_temporal_value(context,progress['records'])
    assert expected['schema_version']==4
    run=context['store'].run_dir
    put(run/'production/scene-upscale/inputs.json',dict(scene_clips_sha256=canonical_digest(expected)))
    monkeypatch.setattr(scene_clip_records,'scene_context',lambda *a,**k:context)
    # Mapping semantics are covered independently; this case isolates the real
    # coordinator's choice of native aggregate schema and downstream digest.
    monkeypatch.setattr('video_ai.planning.scene_clip_continuation.validate_scene_clip_frame_mappings',lambda *a,**k:None)
    monkeypatch.setattr(pipeline,'_continuity_wait',lambda *a:None)
    calls=[]
    def restore(*a,**k):
        calls.append('restore-original-index')
        context['store'].write('complete.json',expected)
        return SimpleNamespace(status='source_clips_ready')
    monkeypatch.setattr('video_ai.runtime.production_scene_clips.produce_scene_clips',restore)
    def forbidden(*a,**k):raise AssertionError('aggregate recovery cannot sample or encode')
    monkeypatch.setattr('video_ai.runtime.temporal_native_process.recover_or_start_native_window',forbidden)
    monkeypatch.setattr('video_ai.runtime.temporal_native_process.recover_or_prepare_native_cache',forbidden)
    with RunLock(run) as held:
        context['store'].lock=held
        result=pipeline._restore_missing_aggregates(context['frozen'],context['units'],context['timeline'],
            paths=runtime_run[2],logger=None,lock=held,deps=SimpleNamespace(wan_client_factory=None,wan_service_factory=None))
    assert result is None,getattr(result,'error',None)
    assert calls==['restore-original-index']
    assert context['store'].read('complete.json')==expected
