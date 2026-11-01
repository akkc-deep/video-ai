"""Read-only recognition of the fixed schema-two scene media promotion proof."""
from pathlib import Path
import re

from .colorimetry import _object,_int
from ..planning.production_scenes import canonical_digest
from ..runtime.manifest import validate_run_dir,_identity,_timestamp
from ..runtime.paths import _validate_spelling

FIELDS='schema_version run_id clip_id operation source staging target recipe evidence created_at'.split()
CLIP_FIELDS=('schema_version production_strategy run_id scene_id clip_id request_sha256 submission_sha256 generated '
    'source frame_mapping_sha256 last_frame_sha256 technical_evidence created_at').split()


def equal(left,right,label):
    if canonical_digest(left)!=canonical_digest(right):raise ValueError('promotion '+label+' differs')


def artifact(value):
    _object(value,('path','bytes','sha256'),'promotion artifact');_int(value['bytes'],'promotion bytes',1)
    if type(value['path']) is not str or type(value['sha256']) is not str or not re.fullmatch('[0-9a-f]{64}',value['sha256']):
        raise ValueError('invalid promotion artifact')
    path=Path(_validate_spelling(value['path']))
    if not path.is_absolute():raise ValueError('absolute promotion artifact required')
    return path


def recipes(b,p):
    for key in ('generated_frames','retained_frames','retained_source_start','retained_source_end','start_frame','end_frame'):
        _int(b[key],key)
    for key in ('width','height'):_int(p[key],key,1)
    a,z=b['retained_source_start'],b['retained_source_end']
    if not 0<=a<z<=b['generated_frames'] or z-a!=b['retained_frames'] or b['end_frame']-b['start_frame']!=z-a:
        raise ValueError('promotion budget interval differs')
    return dict(generated=dict(algorithm='identity_copy_v1',parameters={}),
        source=dict(algorithm='trim_native16_v1',parameters=dict(start_frame=a,end_frame=z,
            filter=f'trim=start_frame={a}:end_frame={z},setpts=N/(16*TB)')),
        last_frame=dict(algorithm='native_index_rgb24_v1',parameters=dict(source_frame_index=z-1,
            expected_frames=b['generated_frames'],width=p['width'],height=p['height'],
            filter=f'select=eq(n\\,{z-1}),format=rgb24')))


def mentions(value,expected):
    if isinstance(value,dict):
        if set(value) in ({'path','bytes','sha256'},{'path','bytes','sha256','mtime_ns','verified_at'}):
            return all(value[k]==expected[k] for k in ('path','bytes','sha256'))
        return any(mentions(v,expected) for v in value.values())
    return isinstance(value,list) and any(mentions(v,expected) for v in value)


class PromotionResolver:
    def __init__(self,window,sidecars):
        self.window=window;self.aliases={};self.proofs=[];self.bound=set()
        for sidecar in sidecars:self._source(sidecar)

    def _read(self,path):
        value=self.window.read_path(path)
        self.proofs.append(self.window.freeze(path))
        return value

    def _source(self,sidecar):
        source=sidecar['source'];path=Path(source['path']);folder=path.parent
        if (path.name!='source.mp4' or folder.parent.name!='scene-clips'
                or folder.parent.parent.name!='production'):return
        run=validate_run_dir(folder.parents[2]);cid=folder.name
        if not re.fullmatch(r'scene_[0-9]+_clip_[0-9]+',cid):return
        declared={r['path']:r for r in sidecar['mapping']['evidence']}
        anchors=[folder/'clip.json',folder/'mapping.json',folder/'media-ready/source.json']
        if any(str(p) not in declared for p in anchors):return
        for p in anchors:self.window.check(declared[str(p)])
        key=(str(folder),source['bytes'],source['sha256'])
        if key in self.bound:return
        self.bound.add(key);self.window.check(source)
        clip=self._read(anchors[0]);mapping=self._read(anchors[1]);_object(clip,CLIP_FIELDS,'promotion clip')
        equal([clip['schema_version'],clip['production_strategy'],clip['run_id'],clip['clip_id']],
            [2,'paragraph_jimeng_v1',run.name,cid],'clip header')
        equal(clip['source'],{k:source[k] for k in ('path','bytes','sha256')},'committed source')
        request=self._read(folder/'request.json');submission=self._read(folder/'submission.json');last=self._read(folder/'last-frame.json')
        for value,label in ((request,'request'),(submission,'submission'),(last,'last-frame')):
            equal([value['schema_version'],value['run_id'],value['clip_id']],[2,run.name,cid],label+' header')
        for value,key_name in ((request,'request_sha256'),(submission,'submission_sha256'),(last,'last_frame_sha256'),(mapping,'frame_mapping_sha256')):
            equal(canonical_digest(value),clip[key_name],key_name)
        b,p=request['budget'],request['parameters'];rules=recipes(b,p)
        for name in ('clip_id','scene_id','generated_frames','retained_frames','start_frame','end_frame'):
            equal(mapping[name],b[name],'mapping '+name)
        equal([b['clip_id'],b['scene_id']],[cid,clip['scene_id']],'budget ids')
        equal([mapping['native_fps'],mapping['output_fps'],p['fps'],p['length']],[16,16,16,b['generated_frames']],'native budget')
        a,z=b['retained_source_start'],b['retained_source_end'];n=b['retained_frames']
        retained=mapping['retained_to_generated'];generated=mapping['generated_to_retained']
        if type(retained) is not list or len(retained)!=n:
            raise ValueError('promotion retained mapping length differs')
        if type(generated) is not list or len(generated)!=b['generated_frames']:
            raise ValueError('promotion generated mapping length differs')
        for index,value in enumerate(retained):
            if type(value) is not int or value!=a+index:
                raise ValueError('promotion retained mapping differs')
        for index,value in enumerate(generated):
            expected=index-a if a<=index<z else None
            if (value is not None if expected is None else type(value) is not int or value!=expected):
                raise ValueError('promotion generated mapping differs')
        for row in sidecar['mapping']['rows']:
            index=row['asset_frame_index'];_int(index,'asset frame')
            if index>=n:raise ValueError('promotion sidecar frame out of range')
            equal([row[k] for k in ('clip_id','generated_frame_index','retained_frame_index','output_frame_index')],
                [cid,a+index,index,b['start_frame']+index],'sidecar mapping')
        equal([p['width'],p['height']],[sidecar['probe']['video']['width'],sidecar['probe']['video']['height']],'dimensions')
        equal(last['generated'],clip['generated'],'last frame generated')
        equal([last['source_frame_index'],last['global_output_frame_index'],last['extraction_rule']],
            [z-1,b['end_frame']-1,'native_index_rgb24_v1'],'last frame mapping')
        specs=(('generated',submission['output'],clip['generated'],folder/'generated.mp4'),
            ('source',clip['generated'],clip['source'],folder/'source.mp4'),
            ('last_frame',clip['generated'],last['image'],folder/f'frame_{z:06d}.png'))
        combined=[]
        for operation,origin,target,final in specs:
            receipt_path=folder/'media-ready'/(operation+'.json');receipt=self._read(receipt_path)
            _object(receipt,FIELDS,'media promotion receipt');_timestamp(receipt['created_at'])
            equal([receipt['schema_version'],receipt['run_id'],receipt['clip_id'],receipt['operation']],
                [2,run.name,cid,operation],'receipt header')
            equal(receipt['source'],origin,'receipt source');equal(receipt['target'],target,'receipt target')
            equal(target['path'],str(final),'fixed target');equal(receipt['recipe'],rules[operation],'recipe')
            self.window.artifact(origin);self.window.artifact(target)
            stage=artifact(receipt['staging'])
            if (stage.name!=final.name or stage.parent.parent!=folder/'staging'
                    or not re.fullmatch('[0-9a-f]{32}',stage.parent.name)
                    or stage!=stage.resolve(strict=False)
                    or any(x.is_symlink() or x.is_junction() for x in (stage,*stage.parents))):
                raise ValueError('promotion staging path differs')
            equal([receipt['staging'][k] for k in ('bytes','sha256')],[target[k] for k in ('bytes','sha256')],'staging bytes')
            if operation=='generated':equal([origin[k] for k in ('bytes','sha256')],[target[k] for k in ('bytes','sha256')],'identity copy')
            if type(receipt['evidence']) is not list:raise ValueError('promotion evidence list required')
            allowed={str(receipt_path)};found=False
            for ref in receipt['evidence']:
                evidence_path=artifact(ref)
                if not evidence_path.is_relative_to(run/'logs/production'):raise ValueError('promotion evidence escapes run')
                self.window.artifact(ref)
                if evidence_path.suffix.lower()=='.json':
                    allowed.add(str(evidence_path));found|=mentions(self._read(evidence_path),receipt['staging'])
            if not found:raise ValueError('promotion lacks original staging identity evidence')
            entry=dict(staging=receipt['staging'],target=target,allowed=allowed)
            if str(stage) in self.aliases:raise ValueError('conflicting media promotion')
            self.aliases[str(stage)]=entry;combined+=receipt['evidence']
            if stage.exists():self.window.artifact(receipt['staging'])
            if operation=='last_frame':equal(last['evidence'],receipt['evidence'],'native evidence')
        equal(clip['technical_evidence'],combined,'technical evidence coverage')

    def resolve(self,identity,document):
        entry=self.aliases.get(identity['path'])
        if entry is None or str(document) not in entry['allowed']:return False
        if set(identity)=={'path','bytes','sha256','mtime_ns','verified_at'}:_identity(identity)
        else:artifact(identity)
        equal({k:identity[k] for k in ('path','bytes','sha256')},entry['staging'],'historical identity')
        if Path(identity['path']).exists():
            if 'mtime_ns' in identity:self.window.check(identity)
            else:self.window.artifact(identity)
        else:
            target=self.window.artifact(entry['target'])
            if 'mtime_ns' in identity:equal(identity['mtime_ns'],target['mtime_ns'],'historical mtime')
        return True

    def verify(self):
        for entry in self.aliases.values():
            self.window.artifact(entry['target'])
            if Path(entry['staging']['path']).exists():self.window.artifact(entry['staging'])
