"""Archive installed repair implementation and dependency inventory as data."""
from pathlib import Path
import os
from uuid import uuid4

from ..planning.production_scenes import canonical_digest
from .manifest import thaw,hash_file
from .production_state import ProductionRefused
from ._scene_continuity_io import artifact,verify,local


def capture_engine():
    from ..media.continuity_report import capture_engine_sources
    from ..media._continuity_schema import stable
    from .paths import SOURCE_ROOT
    from ._scene_color_repair_media import RECIPE
    capture=capture_engine_sources()
    paths=[SOURCE_ROOT/'src/video_ai/media/color_repair.py',SOURCE_ROOT/'scripts/scene_color_repair.py',
        Path(__file__).with_name('scene_color_repair_records.py'),Path(__file__).with_name('production_scene_color_repair.py')]
    paths+=list(Path(__file__).parent.glob('_scene_color_repair_*.py'))
    implementation=[artifact(p,runtime=False) for p in sorted(set(paths))]
    files={r['path']:r for r in capture['files']}
    for path in paths:files[str(path)]=thaw(hash_file(path))
    summary=dict(algorithm='constant_color_repair_v1',implementation=implementation,
        dependency_fingerprint=canonical_digest(dict(continuity_engine=capture['engine'],repair_implementation=implementation,
            python_numpy_opencv=canonical_digest(dict(versions=capture['versions'],build_information=capture['build_information'],
                inventory=stable(capture['files']))))),encoding=RECIPE)
    return dict(engine=summary,versions=capture['versions'],build_information=capture['build_information'],
        files=[files[p] for p in sorted(files)])


def archive_engine(store,folder,capture,*,reader):
    total=sum(row['bytes'] for row in capture['files'])
    if total>536870912:raise ProductionRefused('resource_limit: repair engine 512MiB archive')
    outputs=[]
    for index,ref in enumerate(capture['files']):
        reader.check();store.owned();verify({k:ref[k] for k in ('path','bytes','sha256')},runtime=False,empty=ref['bytes']==0)
        source=local(ref['path'],runtime=False);target=store.root/folder/'engine/files'/f'{index:06d}.bin'
        local(target,exists=False)
        if not target.exists():
            target.parent.mkdir(parents=True,exist_ok=True);temporary=target.with_name(target.name+'.'+uuid4().hex+'.tmp')
            local(temporary,exists=False)
            with source.open('rb') as src,temporary.open('xb') as dst:
                for chunk in iter(lambda:src.read(1048576),b''):
                    reader.check();store.owned();dst.write(chunk)
                dst.flush();os.fsync(dst.fileno())
            store.owned();os.rename(temporary,target)
        copy=artifact(target,empty=ref['bytes']==0)
        if any(copy[k]!=ref[k] for k in ('bytes','sha256')):raise ProductionRefused('repair engine archive bytes differ')
        outputs.append(dict(original=ref,archived=copy))
    build=artifact(store.write_bytes(folder/'engine/build-information.txt',capture['build_information'].encode('utf-8')))
    value=dict(schema_version=1,engine_digest=canonical_digest(capture['engine']),versions=capture['versions'],build_information=build,files=outputs)
    return artifact(store.write(folder/'engine/manifest.json',value))


def verify_engine(folder,intent,*,reader,current=True):
    from .scene_color_repair_records import schema
    value=reader.read(folder/'engine/manifest.json')
    schema(value,'schema_version engine_digest versions build_information files')
    if value['engine_digest']!=canonical_digest(intent['engine']):raise ProductionRefused('repair engine manifest digest differs')
    verify(value['build_information']);seen=set();total=0
    for row in value['files']:
        original=row['original'];saved=row['archived'];verify(saved,empty=saved['bytes']==0)
        if (original['path'] in seen or any(original[k]!=saved[k] for k in ('bytes','sha256')) or
                not Path(saved['path']).is_relative_to(folder/'engine/files')):raise ProductionRefused('repair engine archive invalid')
        seen.add(original['path']);total+=saved['bytes']
        if total>536870912:raise ProductionRefused('resource_limit: repair engine archive')
    for ref in intent['engine']['implementation']:
        if not any(row['original']['path']==ref['path'] and all(row['original'][k]==ref[k] for k in ('bytes','sha256')) for row in value['files']):
            raise ProductionRefused('repair archive lacks implementation')
    if current and capture_engine()['engine']!=intent['engine']:raise ProductionRefused('repair implementation or dependency fingerprint changed')
    return value
