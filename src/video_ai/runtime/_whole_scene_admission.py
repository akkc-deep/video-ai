"""Read-only admission of the one accepted VCO-05 evidence closure.

Archived Python is data: it is hashed, never imported or executed. Current
product Python is deliberately independent of that historical implementation.
"""
import hashlib
import math
import stat
from pathlib import Path

from ..adapters.common import strict_json
from .manifest import hash_file
from .production_state import ArtifactStamp, ProductionRefused, absolute_path, integer, object_fields
from .scene_revision_records import safe_path, stable_bytes
from .verification import verified_read

PINNED_ROOT = Path('D:/VideoSi/cache/video-ai/logs/vco05-20261027-native321')
PINNED_SHA256 = '527f08dd69d51b4c7f176284a768dbf9387deb273d644244920be70c79fcb653'
# The original assessment links media/results, but its resource summary records
# aggregates. Pin that original raw inventory as well so a rewritten sample
# preserving aggregates cannot silently become accepted history.
PINNED_RESOURCE_INVENTORY_SHA256 = '7ec5ca3d2a05e552291d6af6784438a2281a20b82d893a5cf535287d20bb1cee'
PINNED_HTTP_INVENTORY_SHA256 = '61930b293f761367e4012afa8f9fec6ac3e2d3912bc75f0dc4279d30e1fad76c'
PINNED_CASE_SHA256 = '5eef75c3761994614053009a222cbd867ea2ff5ffdbf7bcf7894b82eada6a001'
PINNED_PREPARED_SHA256 = 'e58dcb08ed461ac3eec356b8384be064b60bbec492632048b7102c38add674af'
JSON_LIMIT = 16*1024**2
METADATA_LIMIT = 64*1024**2
ALGORITHM = 'whole_scene_admission_closure_v1'


def require(condition, label):
    if not condition: raise ProductionRefused('whole scene evidence: '+label)


def content(value):
    require(isinstance(value,dict) and set(value) in ({'path','bytes','sha256'}, {'path','bytes','sha256','mtime_ns'}), 'Artifact fields')
    integer(value['bytes'],'evidence bytes')
    path=absolute_path(value['path'])
    digest=value['sha256']
    require(isinstance(digest,str) and len(digest)==64 and all(c in '0123456789abcdef' for c in digest),'Artifact SHA256')
    return dict(path=str(path),bytes=value['bytes'],sha256=digest)


class EvidenceReader:
    """One call's bounded JSON metadata and exact, deduplicated external reads."""
    def __init__(self, reader=None):
        self.reader=reader
        self.artifacts={}
        self.values={}
        self.inventories={}
        self.guards=[]
        self.metadata_bytes=0

    def capture(self,path,expected=None):
        path=absolute_path(str(path));safe_path(path,path.anchor)
        previous=self.artifacts.get(str(path))
        if previous is None:
            stamp=ArtifactStamp.read(path)
            actual=hash_file(path)
            stamp.verify()
            previous=dict(path=str(path),bytes=actual.bytes,sha256=actual.sha256)
            self.artifacts[str(path)]=previous
        if expected is not None: require(previous==content(expected),'changed Artifact: '+str(path))
        return previous

    def raw(self,path):
        path=absolute_path(str(path));safe_path(path,path.anchor)
        require(path.stat().st_size<=JSON_LIMIT,'JSON exceeds 16 MiB')
        raw=stable_bytes(path,root=Path(path.anchor)) if self.reader is None else self.reader(path)
        require(isinstance(raw,bytes) and len(raw)<=JSON_LIMIT,'JSON reader requires bounded bytes')
        identity=dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
        self.capture(path,identity)
        if str(path) not in self.values:
            self.metadata_bytes+=len(raw)
            require(self.metadata_bytes<=METADATA_LIMIT,'metadata exceeds 64 MiB')
        return raw

    def json(self,path,expected=None):
        path=Path(path)
        if str(path) not in self.values:
            self.values[str(path)]=strict_json(self.raw(path).removeprefix(b'\xef\xbb\xbf'))
        if expected is not None:self.capture(path,expected)
        return self.values[str(path)]

    def linked(self,value):
        return self.json(content(value)['path'],value)

    def inventory(self,folder,pattern='*'):
        folder=absolute_path(str(folder));safe_path(folder,folder.anchor)
        require(folder.is_dir(),'missing directory: '+str(folder))
        # Siblings have the same ancestors. Check each distinct parent before
        # and after this scan, retaining the individual file reparse checks.
        # Nothing is cached across inventory calls or byte verifications.
        paths=[];parents=set()
        for path in folder.rglob(pattern):
            if not path.is_file() or '.git' in path.parts or '__pycache__' in path.parts:continue
            parent=path.parent
            if parent not in parents:
                safe_path(parent,folder);parents.add(parent)
            paths.append(path)
            try:metadata=path.lstat()
            except FileNotFoundError:continue
            if stat.S_ISLNK(metadata.st_mode) or getattr(metadata,'st_file_attributes',0)&stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise ProductionRefused('redirected revision evidence path')
        for parent in parents:safe_path(parent,folder)
        safe_path(folder,folder.anchor)
        items=sorted(map(str,paths))
        key=(str(folder),pattern)
        old=self.inventories.get(key)
        require(old is None or old==items,'directory inventory changed')
        self.inventories[key]=items
        from ._continuity_byte_guard import observe_inventory
        observe_inventory(folder,'whole_files',items,pattern=pattern)
        return items

    def verify(self):
        # Reuse is only protected by the existing operation-local Windows handles.
        for path,expected in self.artifacts.items():
            actual=hash_file(Path(path))
            require((actual.bytes,actual.sha256)==(expected['bytes'],expected['sha256']),'changed captured bytes: '+path)
        for (folder,pattern),expected in list(self.inventories.items()):
            require(self.inventory(folder,pattern)==expected,'directory inventory changed')
        for guard in self.guards:guard.verify()


def _media(value,frames,pixel=None):
    for key,expected in dict(width=768,height=432,fps=16,frames=frames,duration=frames/16).items():
        require(type(value.get(key)) in (int,float) and value[key]==expected,'media '+key)
    if pixel:require(value.get('pixel_format')==pixel,'media pixel format')


def _resources(reader,root,summary):
    paths=reader.inventory(root/'resources')
    require(len(paths)==1874,'1874 resource records required')
    require(all(Path(path).suffix=='.json' for path in paths),'resource directory inventory')
    _inventory_pin(reader,root/'resources',paths,PINNED_RESOURCE_INVENTORY_SHA256)
    gpu_peak,rss_peak,system_peak,free_min=0,0,0,float('inf')
    for path in paths:
        sample=reader.json(path)
        require(sample.get('verified') is True,'unverified resource sample')
        pid=sample.get('pid')
        if pid is not None:integer(pid,'resource pid',1)
        records=sample.get('gpu')
        require(isinstance(records,list) and len(records)==2,'resource GPU commands')
        require(all(r.get('returncode')==0 and type(r.get('returncode')) is int for r in records),'resource GPU command failed')
        values=records[0]['stdout'].strip().split(',')
        require(len(values)==5 and 'RTX 5090 D v2' in values[0],'recorded GPU hardware')
        total,used,free,util=(float(x.strip()) for x in values[1:])
        require(all(math.isfinite(x) and x>=0 for x in (total,used,free,util)) and used<=total and free<=total,'resource GPU measurements')
        memory=sample['memory'];system=memory['system_used_bytes'];rss=memory['process_rss_bytes'].get(str(pid),0)
        integer(system,'resource system bytes',1);integer(rss,'resource owned RSS',0 if pid is None else 1)
        require(pid is not None or not memory['process_rss_bytes'],'pre-service resource RSS')
        gpu_peak=max(gpu_peak,used);free_min=min(free_min,free)
        rss_peak=max(rss_peak,rss);system_peak=max(system_peak,system)
    for key,expected in dict(resource_samples=len(paths),verified_samples=len(paths),peak_total_gpu_used_mib=gpu_peak,
        minimum_gpu_free_mib=free_min,peak_owned_service_rss_bytes=rss_peak,peak_system_used_bytes=system_peak).items():
        require(summary.get(key)==expected,'resource summary '+key)


def _case(reader,root):
    case=reader.json(root/'case.json');prepared=reader.json(root/'prepared.json')
    require(reader.capture(root/'case.json')['sha256']==PINNED_CASE_SHA256,'pinned case identity')
    require(reader.capture(root/'prepared.json')['sha256']==PINNED_PREPARED_SHA256,'pinned prepared identity')
    require(case.get('schema_version')==1 and case.get('algorithm')=='wan22_whole_scene_experiment_v1','case schema')
    require(case.get('budget')==dict(requested_frames=321,retained_frames=320,source_start=0,source_end=320,fps=16,duration_seconds=20),'case budget')
    require(prepared.get('case_sha256')==reader.capture(root/'case.json')['sha256'],'prepared case binding')
    graph=reader.linked(case['graph'])
    require(Path(case['graph']['path'])==root/'graph.json','case graph path')
    from ..experiments.whole_scene_case import validate_graph
    from .paths import SOURCE_ROOT
    for name in ('wan22_i2v_14b_api.json','wan22_i2v_14b_api.mapping.json'):
        reader.json(SOURCE_ROOT/'workflows'/name)
    validate_graph(graph)
    inventory=reader.linked(case['source_inventory'])
    require(isinstance(inventory,list) and inventory,'source inventory missing')
    source=absolute_path(case['source_run'])
    require(reader.inventory(source)==sorted(content(v)['path'] for v in inventory),'source directory inventory')
    for value in inventory:reader.capture(value['path'],value)
    dependencies=case['dependencies']
    require(isinstance(dependencies,dict) and dependencies,'case dependencies')
    software={v['path']:v for v in prepared['software']}
    require(len(software)==len(prepared['software']),'duplicate archived software')
    require(reader.inventory(root/'software')==sorted(software),'archived software inventory')
    expected_software=[]
    comfy_paths=[]
    for role,value in dependencies.items():
        if role.startswith('code/'):
            archived=root/'software'/role.removeprefix('code/')
            expected_software.append(str(archived))
            require(str(archived) in software,'missing software archive')
            archived_identity=reader.capture(archived,software[str(archived)])
            require(all(archived_identity[k]==value[k] for k in ('bytes','sha256')),'software archive differs from original identity')
            if role.startswith('code/comfy/'):
                reader.capture(value['path'],value);comfy_paths.append(str(Path(value['path'])))
        else:reader.capture(value['path'],value)
    require(sorted(expected_software)==sorted(software),'unexpected archived software')
    require(comfy_paths,'Comfy software evidence missing')
    require(reader.inventory(case['runtime']['tools']['comfy_root'],'*.py')==sorted(comfy_paths),'current Comfy inventory')
    for role,key in (('start','start'),('prompt_contract','prompt')):
        copy=reader.capture(prepared[key]['path'],prepared[key])
        require(all(copy[k]==dependencies[role][k] for k in ('bytes','sha256')),'prepared '+key+' differs')
    return case,graph


def _submission(reader,root,case,graph,result,summary):
    intent=reader.json(root/'intent.json');submission=reader.json(root/'submission-result.json')
    require(submission==result['submission'] and submission.get('status')=='completed','technical submission differs')
    require(intent.get('case_sha256')==reader.capture(root/'case.json')['sha256'] and intent.get('graph_sha256')==reader.capture(root/'graph.json')['sha256'],'original intent bindings')
    history=submission['history'];status=history['status']
    require(status.get('completed') is True and status.get('status_str')=='success','original history not successful')
    require(history['prompt'][1]==submission['prompt_id'] and history['prompt'][2]==graph and history['prompt'][3]['client_id']==intent['client_id'],'history prompt binding')
    times={row[0]:row[1]['timestamp'] for row in status['messages'] if row[0] in ('execution_start','execution_success')}
    require(set(times)=={'execution_start','execution_success'} and (times['execution_success']-times['execution_start'])/1000==3798.752,'original execution duration')
    posts=[]
    http_paths=reader.inventory(root/'http')
    _inventory_pin(reader,root/'http',http_paths,PINNED_HTTP_INVENTORY_SHA256)
    for path in http_paths:reader.capture(path)
    for path in (p for p in http_paths if p.endswith('.request.json')):
        request=reader.json(path)
        if request.get('method')=='POST':posts.append((Path(path),request))
    require(len(posts)==1 and summary.get('post_count')==1,'exactly one original POST required')
    path,request=posts[0]
    require(request.get('url')=='http://127.0.0.1:8198/prompt' and summary.get('post_routes')==[request['url']],'original POST route')
    require(request['json_body']==dict(prompt=graph,client_id=intent['client_id']),'original POST graph/client')
    response=reader.json(path.with_name(path.name.replace('.request.json','.response.json')))
    require(response.get('status')==200 and response.get('error') is None and response.get('truncated') is False,'original HTTP acceptance')
    body=reader.json(path.with_name(path.name.replace('.request.json','.body')))
    require(body.get('prompt_id')==submission['prompt_id'] and not body.get('node_errors'),'HTTP prompt identity')


def _inventory_pin(reader,root,paths,expected):
    from ..planning.production_scenes import canonical_digest
    rows=[dict(reader.capture(path),path=Path(path).relative_to(root).as_posix()) for path in paths]
    require(canonical_digest(rows)==expected,'pinned raw directory identities: '+str(root))


@verified_read
def load_evidence(path,*,reader=None,allow_frozen=False):
    path=absolute_path(str(path));root=PINNED_ROOT
    require(path==root/'final-assessment.json' or allow_frozen,'accepted evidence root required')
    io=EvidenceReader(reader)
    completion=io.json(root/'completion-check.json')
    assessment=io.json(path)
    require(io.capture(path)['sha256']==PINNED_SHA256,'pinned final assessment SHA256 differs')
    original=io.capture(root/'final-assessment.json',completion['assessment'])
    require(original['sha256']==PINNED_SHA256,'original assessment differs')
    require(completion.get('verified') is True and completion.get('production_mode_enabled') is False,'completion status')
    require(assessment.get('task_id')=='VCO-05' and assessment.get('outcome')=='authorized_first_case_accepted','final assessment outcome')
    require(all(assessment.get(k)=='passed' for k in ('technical','resource_evidence','full_video_observation')),'final acceptance gates')
    require(assessment.get('vco07_first_case_evidence_ready') is True and assessment.get('production_mode_enabled') is False and assessment.get('production_eligible') is False,'first-case scope')
    scope=assessment['scope']
    for key,expected in dict(width=768,height=432,fps=16,retained_frames=320,duration_seconds=20,cross_subject='not_verified_not_authorized',longer_duration='not_verified',multi_window='not_verified').items():
        require(scope.get(key)==expected,'accepted scope '+key)
    observation=io.linked(assessment['observation']);io.capture(completion['user_observation']['path'],assessment['observation'])
    require(content(completion['user_observation'])==content(assessment['observation']),'completion observation binding')
    require(observation.get('reviewer')=='user' and observation.get('review_method')=='human_video' and observation.get('verdict')=='passed','full user observation missing')
    require(observation['coverage'].get('frames')==[0,320] and observation['coverage'].get('duration_seconds')==20,'full observation range')
    require(observation.get('feedback_quote') and observation.get('feedback_source'),'original user feedback provenance')
    require(set(observation['checks'])=={'subject_color','lighting','composition','motion'} and all(v.get('verdict')=='passed' for v in observation['checks'].values()),'user observation checks')
    result=io.linked(assessment['technical_result']);summary=io.linked(assessment['evidence_summary'])
    require(result.get('technical')=='passed' and result.get('status')=='awaiting_video_observation' and result.get('full_video_observation')=='unverified' and result.get('source_unchanged') is True,'historical technical result')
    playback=io.linked(observation['playback_receipt_identity'])
    _media(playback['video'],320,'yuv420p');_media(result['media']['generated'],321);_media(result['media']['review'],320)
    require(playback.get('source_frame_range')==[0,320] and playback.get('lossless') is False,'playback native range')
    for key,media_key in [('generated_identity','generated_identity'),('lossless_review_identity','review_identity'),('mapping_identity','mapping_identity'),('playback_identity',None)]:
        value=content(observation[key]);io.capture(value['path'],value)
        require(value==content(playback[key]),'playback '+key+' binding')
        if media_key:require(value==content(result['media'][media_key]),'result '+key+' binding')
    io.capture(playback['ffmpeg_identity']['path'],playback['ffmpeg_identity'])
    io.linked(playback['probe_identity'])
    mapping=io.linked(observation['mapping_identity'])
    require({k:mapping.get(k) for k in ('requested_frames','retained_frames','source_start','source_end','discarded_source_frames')}==dict(requested_frames=321,retained_frames=320,source_start=0,source_end=320,discarded_source_frames=[320]),'native mapping budget')
    require(mapping.get('frames')==[dict(review_frame=i,source_frame=i,pts=f'{i}/16') for i in range(320)],'native frame mapping')
    native=io.linked(result['media']['native_manifest_identity'])
    require(isinstance(native,list) and len(native)==321,'321 PNG identities required')
    expected=[str(root/'native-frames'/f'frame_{i:06d}.png') for i in range(321)]
    require([content(v)['path'] for v in native]==expected and io.inventory(root/'native-frames')==expected,'native PNG inventory')
    for value in native:io.capture(value['path'],value)
    require(result['media'].get('rgb_preserved') is True and summary.get('rgb_preserved') is True,'native RGB evidence')
    for key,value in dict(raw_frames=321,review_frames=320,review_duration=20,native_png_count=321,mapping_count=320,review_sha256=observation['lossless_review_identity']['sha256'],execution_error_lines=[]).items():
        require(summary.get(key)==value,'evidence summary '+key)
    _resources(io,root,summary)
    case,graph=_case(io,root)
    require(summary.get('source_inventory_count')==len(io.values[str(root/'source-inventory.json')]) and summary.get('dependency_count')==len(case['dependencies']),'summary case inventory')
    _submission(io,root,case,graph,result,summary)
    # Producer code belongs to the historical archive, not today's product tree.
    producer=playback['producer_identity']
    # The compatible playback fix was recorded after initial case preparation;
    # its independently recorded producer must still match its original bytes.
    io.capture(producer['path'],producer)
    io.verify()
    return dict(root=io.capture(path),assessment=assessment,case=case,graph=graph,
        artifacts=sorted(io.artifacts.values(),key=lambda v:v['path']),inventories=io.inventories,guard=io,
        raw=io.raw(path))
