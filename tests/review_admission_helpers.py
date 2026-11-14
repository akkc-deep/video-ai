"""Synthetic three-layer inheritance and shared-ancestor fixture extensions."""
from contextlib import nullcontext
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from video_ai.planning.production_scenes import canonical_digest
from video_ai.runtime import reference_image_records as refs, scene_revision_records as revisions
from video_ai.runtime import _scene_revision_origins as origins, _scene_revision_readers as readers
from video_ai.runtime import production_inputs, scene_clip_records, production_scene_clips


def add_shared_sources(fixture, monkeypatch):
    """Real recursion/guards with synthetic leaf semantics; no media operations."""
    f=fixture; root=f.store.run_dir/'fixture-sources'; root.mkdir()
    config=f.context['frozen'].config
    sources=[]
    for i in range(3):
        run=root/f'source-{i}'; (run/'production').mkdir(parents=True)
        (run/'input.json').write_text(json.dumps({'source':i}),encoding='utf-8')
        sources.append(SimpleNamespace(options={'script_path':str(run/'production/script.txt'),'run_id':run.name},config=config))
    current=f.context['frozen']; all_frozen=[current,*sources]
    guards={}
    for frozen in all_frozen:
        guard=revisions.RevisionGuard(frozen)
        for source in sources:
            path=Path(source.options['script_path']).parent.parent/'input.json'
            guard.capture(path,root=root)
        guards[id(frozen)]=guard
    # A DAG: each layer also directly depends on the shared oldest ancestor.
    for i,frozen in enumerate(all_frozen[:-1]):
        guards[id(frozen)].ancestors=[guards[id(all_frozen[i+1])],guards[id(sources[-1])]]
    keys=['inherited_0001_clip_0001','inherited_0002_clip_0001']
    proofs={}
    for i,frozen in enumerate(all_frozen[:-1]):
        proofs[id(frozen)]={'source_run':Path(all_frozen[i+1].options['script_path']).parent.parent,
            'source_frozen':all_frozen[i+1],'guard':guards[id(frozen)],
            'imports':{'clip:'+key:({'local_artifacts':[]}, {}) for key in keys}}
    f.store.revision_context=proofs[id(current)]
    def proof_for(frozen,domain,key,**kw):
        proof=proofs.get(id(frozen))
        if proof is not None and (domain=='image' or domain+':'+key in proof['imports']): return proof
    monkeypatch.setattr(readers,'proof_for',proof_for)
    def loaded(run):
        f.counts['load_frozen_inputs']+=1
        return next(source for source in sources if Path(source.options['script_path']).parent.parent==run)
    monkeypatch.setattr(production_inputs,'load_frozen_inputs',loaded)
    monkeypatch.setattr(readers,'require_revision_import',lambda frozen,domain,key,**kw:{'clip_id':key})
    monkeypatch.setattr(origins,'_origin_clip_ids',lambda frozen,key:([key],keys))
    monkeypatch.setattr(origins,'_origin_scene_ids',lambda *a:[])
    monkeypatch.setattr('video_ai.runtime._scene_revision_origin_images.origin_image_scope',lambda *a,**kw:nullcontext())
    monkeypatch.setattr('video_ai.runtime._scene_revision_origin_clips.origin_clip_scope',lambda *a,**kw:nullcontext())
    scene={'scene_id':'fixture_reference'}; bible={}; plan={'scenes':[scene]}
    @dataclass
    class Model:
        candidates_per_scene:int=1
    model=Model(); prompt='synthetic fixture reference'; settings={'capability_sha256':'a'*64}
    leaf=Path(sources[-1].options['script_path']).parent.parent
    requests=refs.reference_requests(sources[-1],scene,prompt,[],model)
    provenance=dict(schema_version=2,production_strategy='paragraph_jimeng_v1',run_id=leaf.name,
        scene_id=scene['scene_id'],scene_plan_sha256=canonical_digest(plan),visual_bible_sha256=canonical_digest(bible),
        model_settings={'candidates_per_scene':1},capability_sha256='a'*64,
        prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),references=[],
        requests=[dict(request_id=r['request_id'],logical_request_sha256=canonical_digest(r)) for r in requests])
    folder=leaf/'production/reference-images'/scene['scene_id']; folder.mkdir(parents=True)
    (folder/'provenance.json').write_text(json.dumps(provenance),encoding='utf-8')
    for request in requests:
        folder=leaf/'production/jimeng'/scene['scene_id']/request['request_id']; folder.mkdir(parents=True)
        (folder/'request.json').write_text(json.dumps(request),encoding='utf-8')
        (folder/'intent.json').write_text('{}',encoding='utf-8')
    def committed(*a): f.counts['reference_leaf_rebuild']+=1; return leaf
    monkeypatch.setattr(refs,'_committed',committed)
    monkeypatch.setattr(refs,'load_reference_settings',lambda *a:settings)
    monkeypatch.setattr(refs,'validate_reference_inputs',lambda *a:(model,prompt))
    monkeypatch.setattr(refs,'validate_reference_intent',lambda *a:None)
    monkeypatch.setattr(refs,'validate_submit_evidence',lambda *a:None)
    def common(source):
        origins._json(Path(source.options['script_path']).parent.parent/'input.json',root=root)
        return {'units':{},'timeline':{}}
    monkeypatch.setattr(origins,'common',common)
    monkeypatch.setattr(origins,'origin_timeline',lambda *a:None)
    def source_plan(*a): f.counts['source_plan_rebuild']+=1; return bible,plan
    monkeypatch.setattr(refs.images,'load_committed_plan',source_plan)
    def source_record(source,key):
        f.counts['source_clip_rebuild']+=1
        refs.verify_reference_provenance(source,scene,bible,plan)
        if source is not sources[-1]: return readers.inherited_clip_record(source,key)
        common(source)
        return dict(clip={'clip_id':key},request=dict(budget={'clip_id':key},parameters={},narration_bindings=[],parent=None),
                    accepted={'clip_id':key},rejected=None,template={'clip_id':key})
    monkeypatch.setattr(origins,'_source_clip_record',source_record)
    for module,name in ((origins,'source_clip_record'),(refs,'verify_reference_provenance')):
        original=getattr(module,name)
        def counted(*a,_original=original,_name=name,**kw):
            f.counts[_name]+=1
            return _original(*a,**kw)
        monkeypatch.setattr(module,name,counted)
    ordinary=scene_clip_records.validate_clip
    def validate(context,row,parent=None):
        if row['budget']['clip_id'] in keys:
            f.counts['validate_clip']+=1
            return readers.inherited_clip_record(current,row['budget']['clip_id'],context=f.store.revision_context,row=row,parent=parent)
        return ordinary(context,row,parent)
    monkeypatch.setattr(scene_clip_records,'validate_clip',validate)
    monkeypatch.setattr(production_scene_clips,'validate_clip',validate)
    f.store.clip_ids=frozenset((*f.store.clip_ids,*keys))
    for key in keys:
        sid=key.split('_clip_')[0]
        f.context['rows'].append(dict(budget=dict(scene_id=sid,clip_id=key),parameters={},narration_bindings=[]))
        # The source request retains its source budget; use identical parameters.
        f.context['rows'][-1]['budget']={'scene_id':sid,'clip_id':key}
        f.context['plan']['scenes'].append({'scene_id':sid})
    # Preserve exact row equality in the inherited adapter, including scene ID.
    previous=origins._source_clip_record
    def with_budget(source,key):
        value=previous(source,key)
        value['request']['budget']={'scene_id':key.split('_clip_')[0],'clip_id':key}
        return value
    monkeypatch.setattr(origins,'_source_clip_record',with_budget)
    original_verify=revisions.verify_artifact
    def verified(*a,**kw):
        f.counts['revision_artifact_checks']+=1
        return original_verify(*a,**kw)
    monkeypatch.setattr(revisions,'verify_artifact',verified)
    from video_ai.runtime import manifest
    original_hash=manifest._hash_open_file
    def hashed(stream,path):
        f.counts['hash_reads']+=1
        f.counts['hashed_input_bytes']+=path.stat().st_size
        return original_hash(stream,path)
    monkeypatch.setattr(manifest,'_hash_open_file',hashed)
    return f
