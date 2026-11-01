"""Synthetic transaction records for validation tests; never model/playback evidence."""
from pathlib import Path
from uuid import uuid4

from video_ai.runtime._scene_continuity_io import artifact
from video_ai.runtime.manifest import now, thaw
from video_ai.runtime.workflows import WorkflowTemplate
from scene_continuity_helpers import save


def wan_transaction(run, config):
    evidence = run / 'fixture-evidence'
    selected = evidence / 'selected.png'
    selected.parent.mkdir(parents=True)
    selected.write_bytes(b'fixture-only image; not analyzed or sent to a model')
    model_input = run / 'comfy/input' / run.name / 'material/selected.png'
    model_input.parent.mkdir(parents=True)
    model_input.write_bytes(selected.read_bytes())
    output = run / 'comfy/output' / run.name / 'material/wan_00001_.mp4'
    output.parent.mkdir(parents=True)
    output.write_bytes(b'fixture-only output; not decoded or a real model result')
    options = save(run / 'production/options.json', dict(
        schema_version=1, run_id=run.name, created_at=now(),
        config_snapshot=dict(raw=thaw(config.raw)), model_stamps={k: dict(path=str(config.models[k]),
            bytes=config.models[k].stat().st_size, mtime_ns=config.models[k].stat().st_mtime_ns)
            for k in ('wan_high', 'wan_low', 'text_encoder', 'vae')},
        workflow_snapshots={k: dict(path=str(v), source_identity=artifact(v, runtime=False))
                            for k, v in config.workflows.items() if k in ('wan', 'wan_mapping')}))
    template = WorkflowTemplate.load(config.workflows['wan'], config.workflows['wan_mapping'], config.models)
    params = dict(positive_prompt='fixture-only', start_image=f'{run.name}/material/selected.png',
                  width=768, height=432, length=49, fps=16, seed_high=123, seed_low=0)
    graph = template.instantiate(params, output_prefix=f'{run.name}/material/wan')
    graph_path = save(evidence / 'graph.json', graph)
    conversion = save(evidence / 'conversion.json', dict(created_at=now(), source=artifact(selected), target=artifact(selected)))
    request = save(evidence / 'request.json', dict(schema_version=1, record_kind='real_direct_wan_material_request',
        run_dir=str(run), created_at=now(), selected_image=artifact(selected), actual_model_input=artifact(model_input),
        conversion=artifact(conversion), parameters=params, graph=artifact(graph_path), frozen_options=artifact(options)))
    prompt, client = str(uuid4()), str(uuid4())
    http = run / 'logs/production/http'
    post = save(http / 'post.request.json', dict(method='POST', url='http://127.0.0.1:8188/prompt',
        started_at=now(), json_body=dict(prompt=graph, client_id=client)))
    body = save(http / 'post.body', dict(prompt_id=prompt, node_errors={}, number=0))
    save(http / 'post.response.json', dict(method='POST', url='http://127.0.0.1:8188/prompt',
        status=200, truncated=False, error=None, bytes=body.stat().st_size))
    history = dict(prompt=[0, prompt, graph, dict(client_id=client), ['108']],
        status=dict(completed=True, status_str='success', messages=[['execution_success', dict(prompt_id=prompt)]]),
        outputs={'108': dict(images=[dict(filename=output.name, subfolder=f'{run.name}/material', type='output')])})
    save(http / 'history.request.json', dict(method='GET', url=f'http://127.0.0.1:8188/history/{prompt}',
        started_at=now(), json_body=None))
    body = save(http / 'history.body', {prompt: history})
    save(http / 'history.response.json', dict(status=200, truncated=False, error=None, method='GET',
        url=f'http://127.0.0.1:8188/history/{prompt}', bytes=body.stat().st_size))
    save(run / 'manifest.json', dict(schema_version=1, run_id=run.name,
        inputs=dict(selected_image=artifact(selected)), workflows={'fixture': artifact(graph_path)}))
    result = save(evidence / 'result.json', dict(status='generated', request=artifact(request), prompt_id=prompt,
        original_model_output=artifact(output), video=artifact(output), selected_image=artifact(selected)))
    index = save(evidence / 'index.json', dict(schema_version=1, kind='wan_material_evidence_v1',
        request=artifact(request), result=artifact(result), reference=artifact(conversion), frames=[artifact(conversion)]))
    return dict(index=index, request=request, result=result, post=post, history=http / 'history.body',
                graph=graph_path, selected=selected, model_input=model_input, output=output)
