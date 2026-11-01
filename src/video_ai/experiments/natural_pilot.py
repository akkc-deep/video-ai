"""A separate four-request, development-only stationary-material pilot."""
import json
from pathlib import Path
import sys

import numpy as np

from .natural_acquisition import encode_reference, identity, read_json, verify, write_json
from ..config import load_config
from ..runtime._scene_continuity_io import local
from ..runtime.manifest import now

PILOT_ROOT = Path('D:/VideoSi/projects/video-ai/vco06-natural-qualification/pilots')
FAMILIES = ('woven_display','stone_display','wood_display','tile_display')
PROMPT = ('Locked-off tripod camera observing the exact rigid textured display in the reference. '
          'The camera and all objects remain still throughout the entire shot. '
          'Preserve every edge, position, surface pattern, material and reference color. '
          'Constant soft studio illumination, stable exposure and white balance. '
          'No camera motion, object motion, deformation, folding, falling, new object, '
          'new pattern, lighting change or scene change.')


def render_pilot_reference(index):
    """Author actual sRGB RGB8, with no unknown photo or injected video color."""
    import cv2
    if type(index) is not int or not 0 <= index < 4:
        raise ValueError('four declared pilot references only')
    yy, xx = np.mgrid[:432,:768]
    rng = np.random.default_rng(629290+index)
    grain = cv2.GaussianBlur(rng.normal(0,3,(432,768)).astype(np.float32),(5,5),0)
    base = np.array(((179,176,168),(167,178,181),(184,174,160),(174,181,172))[index])
    rgb = np.clip(base+grain[...,None]+(yy/432-0.5)[...,None]*9,24,232).astype(np.uint8)
    # Stable surround landmarks are part of each authored display, not oracle
    # correspondences or coordinates for the later ordinary tracker.
    for y in range(24,432,32):
        for x in range(24,768,32):
            cv2.rectangle(rgb,(x,y),(x+3,y+3),(104+index*5,107,102),-1)
    colors = ((151,83,65),(69,126,147),(163,153,84))
    for j, color in enumerate(colors):
        x0=62+j*231; y0=94+(j%2)*24
        cv2.rectangle(rgb,(x0+8,y0+10),(x0+188,y0+224),(112,108,101),-1)
        cv2.rectangle(rgb,(x0,y0),(x0+180,y0+214),(60,65,61),-1)
        rect=rgb[y0+5:y0+210,x0+5:x0+176]
        h,w=rect.shape[:2]; py,px=np.mgrid[:h,:w]
        if index == 0: pattern=((px//6+py//6)%2)*12-6
        elif index == 1: pattern=cv2.GaussianBlur(rng.normal(0,12,(h,w)).astype(np.float32),(7,7),0)
        elif index == 2: pattern=7*np.sin(px*.32+2*np.sin(py*.055))
        else: pattern=np.where((px%36<3)|(py%41<3),-21,4)
        rect[:]=np.clip(np.asarray(color)+pattern[...,None]+(py/h-.5)[...,None]*7,24,232).astype(np.uint8)
        for k in range(3):
            cx=x0+28+k*51;cy=y0+35+(j+k)%3*49
            cv2.circle(rgb,(cx,cy),5,(204,194,169),-1)
    return rgb


def _cases(references):
    return [dict(case_id=f'p{i+1:02d}_{family}',scene_group=f'p{i+1:02d}_{family}',split='development',
        reference=r['reference'],conversion=r['conversion'],frames=49,fps='16/1',width=768,height=432,
        seed_high=629290000000000+i,seed_low=0,positive_prompt=PROMPT,natural_label='unverified')
        for i,(family,r) in enumerate(zip(FAMILIES,references))]


def validate_pilot(plan):
    keys=('schema_version kind created_at max_requests expected_motion reference_domain config cases models '
          'software dependencies production_eligible qualification seen_exclusions retry_policy').split()
    if (type(plan) is not dict or set(plan)!=set(keys) or type(plan['schema_version']) is not int
            or plan['schema_version']!=1 or plan['kind']!='natural_material_stationary_pilot_v1'
            or type(plan['max_requests']) is not int or plan['max_requests']!=4
            or plan['expected_motion']!='stationary_camera_and_objects'
            or plan['reference_domain']!='authored_srgb_textured_stationary_display'
            or plan['production_eligible'] is not False or plan['qualification']!='exploratory_development_only'
            or plan['retry_policy']!='Same original request only; no replacement or automatic new POST.'
            or type(plan['cases']) is not list or len(plan['cases'])!=4):
        raise ValueError('exact four-request development pilot schema required')
    cases=plan['cases']
    if cases!=_cases(cases) or len({c['reference']['sha256'] for c in cases})!=4:
        raise ValueError('frozen pilot case, prompt, seed, intent or unknown label differs')
    if [m['role'] for m in plan['models']]!=['wan_high','wan_low','text_encoder','vae']:
        raise ValueError('four actual generation model stamps required')
    return plan


def _root(root, exists=False):
    root=local(root,exists=False)
    if root==PILOT_ROOT or not root.is_relative_to(PILOT_ROOT):
        raise ValueError('new independent pilot root required')
    if exists and not root.is_dir(): raise ValueError('pilot directory unavailable')
    return root


def freeze_pilot(root, config_path):
    root=_root(root)
    if root.exists(): raise FileExistsError('pilot already exists; never overwrite')
    config=load_config(Path(config_path))
    raw=json.loads(Path(config_path).read_text(encoding='utf-8-sig'))
    if raw.get('production_strategy')!='paragraph_jimeng_v1':
        raise ValueError('direct Wan pilot requires existing paragraph_jimeng_v1 config')
    for key in ('runtime_root','project_root','output_root','cache_root'):
        raw[key]=str(getattr(config,key))
    raw['voice_config']=str(config.voice.config_file)
    for key in ('tools','models','workflows'):
        raw[key]={k:str(v) for k,v in getattr(config,key).items()}
    for key in ('font_file','music'):
        value=getattr(config.media,key)
        if value is not None: raw['media'][key]=str(value)
    raw['scene_continuity']=dict(schema_version=1,policy='advisory_v1')
    root.mkdir(parents=True)
    config_ref=write_json(root/'generation-config.json',raw)
    load_config(Path(config_ref['path']))
    archive=root/'reference-renderer.py'
    with archive.open('xb') as stream: stream.write(Path(__file__).read_bytes())
    references=[]
    for i,family in enumerate(FAMILIES):
        folder=root/'references'/f'p{i+1:02d}_{family}';folder.mkdir(parents=True)
        image=folder/'selected-reference-srgb.png'
        with image.open('xb') as stream: stream.write(encode_reference(render_pilot_reference(i)))
        reference=identity(image)
        conversion=write_json(folder/'reference-conversion.json',dict(created_at=now(),target=reference,
            source_kind='authored_srgb_stationary_pilot_v1',source=identity(archive),scene_index=i,
            operation='Direct sRGB RGB8 authorship; no unknown input pixels or injected video bias.',
            target_color_intent='Preserve the authored palette, fixed lighting, stationary camera and objects.',
            limitation='Exploratory shared-tool display, not photographic evidence or an independent qualification group.'))
        references.append(dict(reference=reference,conversion=conversion))
    models=[]
    for name in ('wan_high','wan_low','text_encoder','vae'):
        path=config.models[name];stat=path.stat()
        models.append(dict(role=name,path=str(path),bytes=stat.st_size,mtime_ns=stat.st_mtime_ns))
    folder=Path(__file__).parent
    software=[identity(p) for p in sorted(folder.glob('natural_acquisition*.py'))]
    software += [identity(p) for p in (Path(__file__),folder/'natural_pilot_runtime.py',
        folder/'natural_material_preparation.py',folder.parents[2]/'scripts/experiments/vco06_pilot.py') if p.is_file()]
    base=folder.parent
    critical=('config.py adapters/common.py adapters/comfyui.py media/colorimetry.py media/video.py '
        'runtime/production_inputs.py runtime/production_comfy.py runtime/production_visual_templates.py runtime/workflows.py '
        'runtime/services.py runtime/service_specs.py runtime/owned_cleanup.py runtime/processes.py '
        'runtime/environment.py runtime/logging.py runtime/manifest.py runtime/paths.py runtime/production_state.py '
        'runtime/production_research_material.py runtime/research_material_records.py').split()
    software += [identity(base/name) for name in critical]
    software=sorted({p['path']:p for p in software}.values(),key=lambda p:p['path'])
    executable_paths=[Path(sys.executable),config.tools['comfy_python'],config.tools['ffmpeg'],config.tools['ffprobe'],
        config.tools['comfy_root']/'main.py']
    dependencies=[identity(archive),*[identity(config.workflows[k]) for k in ('wan','wan_mapping')],
        *[identity(p) for p in executable_paths]]
    plan=validate_pilot(dict(schema_version=1,kind='natural_material_stationary_pilot_v1',created_at=now(),
        max_requests=4,expected_motion='stationary_camera_and_objects',reference_domain='authored_srgb_textured_stationary_display',
        config=config_ref,cases=_cases(references),models=models,software=software,dependencies=dependencies,
        production_eligible=False,qualification='exploratory_development_only',
        seen_exclusions=['all previous outputs and holdouts','all pilot outputs are development_seen; shared authored materials are not independent blinded groups'],
        retry_policy='Same original request only; no replacement or automatic new POST.'))
    frozen=write_json(root/'pilot.FROZEN.json',plan)
    write_json(root/'collection-receipt.json',dict(collection=frozen))
    return plan


def load_pilot(root):
    root=_root(root,exists=True)
    receipt=read_json(root/'collection-receipt.json')
    if set(receipt)!={'collection'} or Path(receipt['collection']['path'])!=root/'pilot.FROZEN.json':
        raise ValueError('foreign pilot frozen identity')
    plan=validate_pilot(read_json(verify(receipt['collection'])))
    for item in [plan['config'],*plan['software'],*plan['dependencies']]: verify(item)
    for case in plan['cases']:
        verify(case['reference']);verify(case['conversion'])
        conversion=read_json(case['conversion']['path'])
        if conversion['target']!=case['reference']:
            raise ValueError('pilot reference conversion identity differs')
        verify(conversion['source'])
    for model in plan['models']:
        path=Path(model['path']);stat=path.stat()
        if path!=path.resolve(strict=True) or stat.st_size!=model['bytes'] or stat.st_mtime_ns!=model['mtime_ns']:
            raise ValueError('pilot model stamp identity differs')
    return plan


def pilot_case(root, case_id):
    plan=load_pilot(root)
    matches=[c for c in plan['cases'] if c['case_id']==case_id]
    if len(matches)!=1: raise ValueError('unknown frozen pilot case')
    return plan,matches[0],Path(root)/'cases'/case_id
