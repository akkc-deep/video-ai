"""Strict natural-study input identities and immutable, bounded local records."""
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from ._scene_continuity_io import artifact,instant,local,uid
from .manifest import now
from .production_state import object_fields,ProductionRefused
from .research_material_records import ResearchReader,load_research_material_context,ref

STUDY_ROOT=Path('D:/VideoSi/projects/video-ai/vco06-natural-qualification/studies')
REQUEST='schema_version study_id config conditional_profile seen cases requested_at reason'
CASE='case_id scene_group group_basis domain split material manifest observations'


def fields(value,names,label='natural study'):
    object_fields(value,names.split() if isinstance(names,str) else names,label)
    if 'schema_version' in value and (type(value['schema_version']) is not int or value['schema_version']!=1):
        raise ProductionRefused('natural schema1 non-Boolean version required')
    return value


def text(value):
    if type(value) is not str or not value.strip(): raise ProductionRefused('nonempty natural-study text required')
    return value


def timestamp(value):
    if type(value) is not str: raise ProductionRefused('actual timestamp string required')
    result=instant(value)
    if result>datetime.now(timezone.utc): raise ProductionRefused('future natural-study timestamp')
    return result


class StudyReader(ResearchReader):
    def charge(self,path,size):
        self.check()
        if type(size) is not int or not 0<=size<=16*1024**2: raise ProductionRefused('resource_limit: study JSON')
        key=str(path)
        if key in self.json_paths and self.json_paths[key]!=size: raise ProductionRefused('study metadata size changed')
        self.json_paths[key]=size
        if sum(self.json_paths.values())>256*1024**2: raise ProductionRefused('resource_limit: study cumulative JSON')

    def any(self,value):
        path=Path(value['path'] if isinstance(value,dict) else value)
        return self.read(value,package=not path.is_relative_to(Path('D:/VideoSi')))

    def cap(self,value):
        path=Path(value['path'] if isinstance(value,dict) else value)
        result=self.capture(value,package=not path.is_relative_to(Path('D:/VideoSi')))
        if result['bytes']==0: raise ProductionRefused('empty natural-study input')
        return result


def put_json(path,value):
    raw=(json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n').encode('utf-8')
    return put_bytes(path,raw)


def put_bytes(path,raw):
    if len(raw)>16*1024**2: raise ProductionRefused('resource_limit: study output JSON')
    path=local(path,exists=False)
    if path.exists():
        local(path)
        if path.read_bytes()!=raw: raise ProductionRefused('immutable study output differs')
        return artifact(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.'+uuid4().hex+'.tmp')
    with temporary.open('xb') as stream: stream.write(raw);stream.flush();os.fsync(stream.fileno())
    # Windows rename refuses an already-created destination; never replace.
    os.rename(temporary,path)
    return artifact(path)


def copy_original(ref,path):
    r=StudyReader();value=r.cap(ref)
    if value['bytes']>16*1024**2: raise ProductionRefused('resource_limit: original JSON bytes')
    raw=Path(value['path']).read_bytes()
    if len(raw)!=value['bytes'] or hashlib.sha256(raw).hexdigest()!=value['sha256']: raise ProductionRefused('original bytes changed during copy')
    copied=put_bytes(path,raw);r.verify_all();return copied


class StudyLock:
    def __init__(self,root):
        self.root=local(root,exists=False);self.path=self.root/'.natural-study.lock'
        self.owner=dict(pid=os.getpid(),token=uuid4().hex,created_at=now())
    def __enter__(self):
        self.root.mkdir(parents=True,exist_ok=True)
        raw=(json.dumps(self.owner,separators=(',',':'))+'\n').encode()
        try:
            with self.path.open('xb') as stream: stream.write(raw);stream.flush();os.fsync(stream.fileno())
        except FileExistsError as error: raise RuntimeError('natural study already locked; unknown owner retained') from error
        return self
    def owned(self):
        if StudyReader().any(self.path)!=self.owner: raise ProductionRefused('natural-study lock owner changed; retained')
    def __exit__(self,typ,value,tb):
        self.owned();self.path.unlink();return False


def study_root(root,study_id=None):
    path=local(root,exists=False)
    uid(path.name)
    if path.parent!=STUDY_ROOT: raise ProductionRefused('independent canonical natural-study root required')
    if study_id is not None and path.name!=uid(study_id): raise ProductionRefused('study UUID/root binding differs')
    return path


def bind_manifest(case,context,reader):
    from ..media.research_pair_report import _full_manifest
    manifest=_full_manifest(reader.any(case['manifest']))
    if ([ref(f['record']) for f in manifest['clips'][0]['frames']]!=context['frames']
            or ref(manifest['references'][0]['record'])!=context['reference']
            or manifest['domain']['source_kind']!='generated' or manifest['timeline']!=dict(fps_num=16,fps_den=1)):
        raise ProductionRefused('natural manifest original source/reference/native frame binding differs')
    reader.cap(manifest['regions'])
    if manifest['context'] is not None: reader.cap(manifest['context'])
    return manifest


def observation_sources(context,reader):
    commit=reader.any(context['commit']);index=reader.any(commit['origin']['source_index'])
    result=reader.any(index['result']);request=reader.any(index['request'])
    videos=[context['source'],result['video'],result['original_model_output']]
    images=[context['selected_image'],request['selected_image']]
    return videos,images,result.get('finished_at',request['created_at'])


def read_author_observations(case,context,reader):
    from ..experiments.natural_acquisition_observation import validate_observation
    from ..experiments.natural_remote_observation import validate_remote_observation
    videos,images,generated_at=observation_sources(context,reader)
    records=[];hard_failure=False;unresolved=False
    for item in case['observations']:
        row=reader.any(item)
        if (type(row) is not dict or row.get('case_id')!=case['case_id'] or row.get('video') not in videos or row.get('reference') not in images):
            raise ProductionRefused('original author observation source/case/reference binding differs')
        kind=row.get('kind')
        if kind=='natural_material_observation_draft_v1':
            f=row.get('form')
            if type(f) is not dict: raise ProductionRefused('original draft form required')
            timestamp(row['saved_at']);unresolved=True
            hard_failure |= f.get('subject_structure_intact') is False or f.get('motion_intact') is False
            records.append(dict(natural_label='unverified',operation=None,correction_direction=None,
                target_reference_confirmed=f.get('target_reference_confirmed'),subject_structure_intact=f.get('subject_structure_intact'),
                motion_intact=f.get('motion_intact'),intentional_lighting_change=f.get('intentional_lighting_change')))
            continue
        state=validate_remote_observation(row) if kind=='natural_material_observation_remote_v2' else validate_observation(row)
        if generated_at is not None and timestamp(row['reviewed_at'])<timestamp(generated_at):
            raise ProductionRefused('observation predates original generated media')
        if state!='unverified':
            if row['playback']['frames']!=len(context['frames']): raise ProductionRefused('observation native frame coverage differs')
            if generated_at is not None and timestamp(row['playback']['started_at'])<timestamp(generated_at):
                raise ProductionRefused('actual viewing predates generated media')
        unresolved |= row['natural_label']=='unverified'
        hard_failure |= row['subject_structure_intact'] is False or row['motion_intact'] is False
        records.append({k:row[k] for k in ('natural_label','operation','correction_direction','target_reference_confirmed',
            'subject_structure_intact','motion_intact','intentional_lighting_change')})
    latest=records[-1]
    # A new positive cannot erase an older confirmed non-color failure, or an
    # unresolved submitted label. Explicit source responses belong to precheck.
    return dict(**latest,unresolved=unresolved,hard_noncolor_failure=bool(hard_failure))


def registered_observation_refs(context,reader):
    """Only byte identities here: safe for a sealed-but-unopened holdout."""
    commit=reader.any(context['commit']);index_ref=commit['origin']['source_index'];index=reader.any(index_ref)
    result=reader.any(index['result']);cid=text(result.get('case_id'));index_path=Path(index_ref['path'])
    if index_path.parent.name!=cid or index_path.parent.parent.name!='cases':
        raise ProductionRefused('registered natural source observation history unavailable')
    collection=index_path.parents[2];found={}
    for name in ('observations','remote-observations','observation-drafts'):
        folder=collection/name/cid
        if folder.exists():
            local(folder,exists=False)
            for path in folder.glob('*.json'):
                if len(found)>=512: raise ProductionRefused('resource_limit: original observation history')
                value=reader.cap(path);found[value['sha256']]=value
    return cid,[found[k] for k in sorted(found)]


def require_complete_observations(case,context,reader):
    cid,registered=registered_observation_refs(context,reader)
    supplied={reader.cap(r)['sha256'] for r in case['observations']}
    if cid!=case['case_id'] or any(r['sha256'] not in supplied for r in registered):
        raise ProductionRefused('submitted observations omit registered source history')


def _seen(value):
    fields(value,'schema_version video_sha256 reference_sha256')
    if type(value['schema_version']) is not int or value['schema_version']!=1: raise ProductionRefused('seen index schema differs')
    for name in ('video_sha256','reference_sha256'):
        items=value[name]
        if (type(items) is not list or any(type(x) is not str or not re.fullmatch('[0-9a-f]{64}',x) for x in items)
                or items!=sorted(set(items))): raise ProductionRefused('sorted unique seen content SHA required')
    return value


def holdout_reservations(request,metadata,*,reserve=False):
    """A new UUID cannot erase prior blind-source use or a partial trial."""
    root=STUDY_ROOT.parent/'natural-study-holdout-reservations'
    owner=dict(schema_version=1,study_id=request['study_id'],root=str(STUDY_ROOT/request['study_id']))
    def check():
        r=StudyReader()
        for row in metadata:
            if row['split']!='holdout': continue
            for kind,key in [('video','source'),('reference','reference')]:
                path=root/(kind+'-'+row[key]['sha256']+'.json')
                if path.exists() and r.any(path)!=owner: raise ProductionRefused('holdout source/reference already reserved by an earlier study')
                if reserve: put_json(path,owner)
        r.verify_all()
    if reserve:
        with StudyLock(root): check()
    else: check()


def opaque_holdout_context(run,reader):
    """Verify original transaction and byte identities without opening RGB/labels."""
    from ..config import load_config
    from .research_material_records import verify_wan_material
    material=reader.cap(run/'research/material/commit.json');commit=reader.any(material)
    fields(commit,'schema_version kind run_id material_id request origin selected_image source frame_map last_frame color_analysis closure created_at')
    options_ref=reader.cap(run/'research/options.json');options=reader.any(options_ref)
    request=reader.any(commit['request'])
    if (commit['kind']!='research_wan_material_v1' or commit['run_id']!=run.name
            or options['execution_mode']!='research' or options['source_kind']!=commit['kind']
            or options['scene_research_material']['commit']!=material
            or request['source_index']!=commit['origin']['source_index'] or request['config']!=options['config']):
        raise ProductionRefused('blind original import producer differs')
    config=load_config(Path(reader.cap(options['config'])['path']))
    source=verify_wan_material(commit['origin']['source_index'],config=config,_reader=reader)
    for item in commit['closure']: reader.capture(item,package=True)
    for k in ('source','selected_image'):
        kept=reader.cap(commit[k])
        if (kept['bytes'],kept['sha256'])!=(source[k]['bytes'],source[k]['sha256']):
            raise ProductionRefused('blind retained source differs')
    epoch_ref=reader.cap(run/'research/continuity/epoch.json');epoch=reader.any(epoch_ref)
    if epoch!=dict(schema_version=1,run_id=run.name,source_kind=commit['kind'],commit=material,options=options_ref,created_at=commit['created_at']):
        raise ProductionRefused('blind original epoch differs')
    reader.cap(commit['frame_map']);reader.cap(commit['last_frame']);reader.cap(commit['color_analysis'])
    return dict(source_kind=commit['kind'],source=commit['source'],selected_image=commit['selected_image'],
        commit=material,epoch=epoch_ref,frames=source['frames'],reference=source['reference'],assessment=None)


def case_context(case,reader,*,open_holdout=False):
    material=reader.cap(case['material']);path=Path(material['path'])
    if path.parts[-3:]!=('research','material','commit.json'): raise ProductionRefused('canonical research material commit required')
    run=path.parents[2]
    if case['split']=='holdout' and (run/'research/continuity/assessment.json').exists():
        raise ProductionRefused('previously measured holdout material is not blind')
    context=(opaque_holdout_context(run,reader) if case['split']=='holdout' and not open_holdout
        else load_research_material_context(run,reader=reader))
    if context['commit']!=material or context['source_kind']!='research_wan_material_v1':
        raise ProductionRefused('actual research source/commit differs')
    bind_manifest(case,context,reader)
    bind_source_registration(case,context,reader)
    require_complete_observations(case,context,reader)
    return context


def bind_source_registration(case,context,reader):
    commit=reader.any(context['commit']);index=reader.any(commit['origin']['source_index']);result=reader.any(index['result'])
    if any(result.get(k)!=case[k] for k in ('case_id','scene_group','split')):
        raise ProductionRefused('original generation case/family/split registration differs')
    manifest=reader.any(case['manifest'])
    if case['domain']!=manifest['domain']['genre']: raise ProductionRefused('original manifest domain registration differs')


def check_inputs(request,*,require_complete=True):
    fields(request,REQUEST)
    if type(request['schema_version']) is not int or request['schema_version']!=1: raise ProductionRefused('natural study schema1 required')
    uid(request['study_id']);timestamp(request['requested_at']);text(request['reason'])
    reader=StudyReader()
    for name in ('config','conditional_profile'): reader.cap(request[name])
    seen=_seen(reader.any(request['seen']))
    cases=request['cases']
    if type(cases) is not list or not 1<=len(cases)<=512: raise ProductionRefused('bounded explicit natural cases required')
    ids=set();groups={'development':set(),'holdout':set()};counts={'development':0,'holdout':0}
    reference_groups={};videos=set();metadata=[]
    for case in cases:
        fields(case,CASE)
        for name in ('case_id','scene_group','group_basis','domain'): text(case[name])
        if not re.fullmatch('[A-Za-z0-9_-]+',case['case_id']) or case['case_id'] in ids: raise ProductionRefused('unique canonical study case IDs required')
        ids.add(case['case_id']);split=case['split']
        if split not in counts: raise ProductionRefused('explicit development/holdout split required')
        counts[split]+=1;groups[split].add(case['scene_group'])
        if groups['development']&groups['holdout']: raise ProductionRefused('source group crosses split')
        if type(case['observations']) is not list or not 1<=len(case['observations'])<=512:
            raise ProductionRefused('actual observation identities required')
        if len({(v['path'],v['sha256']) for v in case['observations']})!=len(case['observations']):
            raise ProductionRefused('duplicate observation submission identity')
        # Each source is one bounded operation. Keep only the small resulting
        # metadata; never accumulate every decoded case's JSON at once.
        source_reader=StudyReader();context=case_context(case,source_reader)
        v,r=context['source']['sha256'],context['selected_image']['sha256']
        if v in videos: raise ProductionRefused('same original video counted twice')
        videos.add(v)
        prior=reference_groups.setdefault(r,(case['scene_group'],split))
        if prior!=(case['scene_group'],split): raise ProductionRefused('same reference crosses family/group/split')
        if split=='holdout' and (v in seen['video_sha256'] or r in seen['reference_sha256']):
            raise ProductionRefused('seen material/reference cannot be new holdout')
        for observation in case['observations']: source_reader.cap(observation)
        author=None if split=='holdout' else read_author_observations(case,context,source_reader)
        source_reader.verify_all()
        metadata.append(dict(case_id=case['case_id'],split=split,source=context['source'],reference=context['selected_image'],
            material=context['commit'],epoch=context['epoch'],frames=len(context['frames']),author=author))
    complete=all(counts[s]>=12 and len(groups[s])>=4 for s in counts)
    holdout_reservations(request,metadata)
    if require_complete and not complete: raise ProductionRefused('each split needs12 complete videos and4 non-overlapping groups')
    reader.verify_all()
    return dict(structurally_complete=complete,cases=len(cases),development_cases=counts['development'],holdout_cases=counts['holdout'],
        groups={s:sorted(v) for s,v in groups.items()},metadata=metadata,holdout_labels_opened=False,ready_for_propose=False)


def capture_software(config=None):
    from ..media.continuity_report import capture_engine_sources
    from ..media._continuity_schema import stable
    capture=capture_engine_sources()
    base=Path(__file__).parent;source=base.parent
    files={p['path']:ref(p) for p in capture['files']}
    names=('natural_study_records.py','natural_study_measure.py','natural_study.py','natural_repair_profile.py',
        'natural_candidate_records.py','natural_candidate_media.py','production_natural_repair.py')
    paths=[base/n for n in names]+[source/'media'/n for n in ('natural_repair_engine.py','natural_color_repair.py',
        'natural_repair_statistics.py','color_repair.py')]
    paths += [base/n for n in ('research_material_records.py','research_material_baseline.py','_scene_color_repair_profile.py',
        '_scene_color_repair_media.py','_scene_color_repair_validation.py','production_research_material.py',
        'manifest.py','paths.py','logging.py','environment.py','processes.py')]
    paths += [source/'media/research_pair_report.py',source/'config.py']
    paths += [source.parents[1]/'scripts/experiments/vco06_natural_study.py',source.parents[1]/'scripts/natural_color_repair.py']
    if config is not None: paths += [config.tools[n] for n in ('ffmpeg','ffprobe')]
    for path in paths:
        if path.is_file(): files[str(path)]=artifact(path,runtime=False)
    return dict(schema_version=1,algorithm='natural_constant_color_repair_v1',versions=capture['versions'],
        engine=stable(capture['engine']),build_information_sha256=hashlib.sha256(capture['build_information'].encode()).hexdigest(),
        files=[files[k] for k in sorted(files)])


def verify_software(saved,config=None):
    if capture_software(config)!=saved: raise ProductionRefused('frozen natural-study software or dependency inventory drift')
    return saved
