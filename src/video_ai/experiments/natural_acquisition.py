"""Preregister new real-model material acquisition; never assigns natural labels."""
import hashlib
import json
import os
from pathlib import Path

import numpy as np

from ..config import load_config
from ..media._continuity_audit import png_bytes
from ..runtime._scene_continuity_io import local
from ..runtime.manifest import now

COLLECTION_ROOT = Path('D:/VideoSi/projects/video-ai/vco06-natural-qualification')
SCENES = ('ceramic_spheres', 'faceted_blocks', 'paper_folds', 'wooden_tiles',
          'woven_cushions', 'stone_pebbles', 'brushed_metal', 'plaster_arches')
PROMPT = ('A very slow continuous horizontal camera slide across the exact still life in the reference. '
          'All objects stay rigid with the same positions, shapes, colors and surface materials. '
          'Constant soft studio illumination, stable exposure and white balance. '
          'Preserve the fine surface texture. No scene change, object deformation or material change.')


def identity(path):
    path = Path(path)
    before = path.stat()
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError('identity changed during read')
    return dict(path=str(path), bytes=after.st_size, sha256=digest)


def verify(value):
    path = Path(value['path'])
    # Evidence uses local single-link files. Shared large model files use stamps separately.
    if (not path.is_absolute() or path != path.resolve(strict=True)
            or path.stat().st_nlink != 1 or any(p.is_symlink() or p.is_junction() for p in (path, *path.parents))
            or identity(path) != value):
        raise ValueError('frozen acquisition identity differs: ' + str(path))
    return path


def write_json(path, value):
    raw = (json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))+'\n').encode()
    if len(raw) > 16 * 1024**2:
        raise ValueError('acquisition JSON exceeds 16MiB')
    path = local(path, exists=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return identity(path)


def read_json(path):
    from ..adapters.common import strict_json
    path = local(path)
    if path.stat().st_size > 16 * 1024**2:
        raise ValueError('acquisition JSON exceeds 16MiB')
    return strict_json(path.read_bytes())


def render_reference(scene_index):
    """Author RGB8 sRGB code values directly, not relabeling an unknown source image.

    Independent geometry/material families share a deterministic rendering tool.
    This is a restricted authored still-life domain, not photographic evidence.
    """
    if type(scene_index) is not int or not 0 <= scene_index < 8:
        raise ValueError('eight declared scene indices only')
    import cv2
    h, w = 432, 768
    yy, xx = np.mgrid[:h, :w]
    rng = np.random.default_rng(627100 + scene_index)
    bases = [(191, 183, 168), (170, 183, 188), (197, 186, 178), (174, 185, 166),
             (182, 177, 193), (181, 190, 182), (193, 180, 166), (179, 186, 193)]
    grain = rng.normal(0, 1.8, (h, w))
    background = np.array(bases[scene_index])[None, None, :] * (.90 + .10 * yy[..., None]/h)
    image = np.clip(background + grain[..., None], 4, 251).astype(np.uint8)
    cv2.line(image, (0, 303), (767, 303), (145, 143, 140), 2)
    for j in range(3):
        cx, cy = 164 + j*213 + (scene_index % 3)*5, 244 + ((j+scene_index)%3-1)*23
        rx, ry = 61 + (scene_index*7+j*11)%24, 54 + (scene_index*13+j*7)%32
        shadow = np.zeros((h, w), np.uint8)
        cv2.ellipse(shadow, (cx+16, cy+ry-2), (rx+14, 13), 0, 0, 360, 255, -1)
        shadow = cv2.GaussianBlur(shadow, (31, 31), 7)/255
        image = np.rint(image.astype(float)*(1-.18*shadow[..., None])).astype(np.uint8)
        mask = np.zeros((h, w), np.uint8)
        if scene_index in (0, 5):
            cv2.ellipse(mask, (cx, cy), (rx, ry), j*13, 0, 360, 255, -1)
        elif scene_index in (1, 2):
            corners = np.array([[cx-rx,cy+ry],[cx-rx+13,cy-ry//2], [cx+rx//3,cy-ry], [cx+rx,cy+ry-9]])
            cv2.fillConvexPoly(mask, corners, 255)
        elif scene_index == 7:
            cv2.rectangle(mask, (cx-rx,cy), (cx+rx,cy+ry),255,-1)
            cv2.ellipse(mask,(cx,cy),(rx,ry),0,180,360,255,-1)
            cv2.rectangle(mask,(cx-rx//2,cy),(cx+rx//2,cy+ry),0,-1)
            cv2.ellipse(mask,(cx,cy),(rx//2,ry//2),0,180,360,0,-1)
        else:
            cv2.rectangle(mask, (cx-rx,cy-ry), (cx+rx,cy+ry),255,-1)
        dx, dy = (xx-cx)/rx, (yy-cy)/ry
        shade = .86 + .13*np.clip(-dx-dy, -1, 1)
        palette = np.array([(187,147,124),(146,169,177),(194,187,157)])[j]
        if scene_index == 3:
            texture = 4*np.sin(xx*.18 + 2*np.sin(yy*.04)) + grain
        elif scene_index == 4:
            texture = 3*np.sin(xx*1.1) + 3*np.sin(yy*1.2) + grain
        elif scene_index == 6:
            texture = 4*np.sin(yy*.65) + grain*.7
        elif scene_index in (1, 2):
            texture = 7*(dx+dy > 0) + grain*.7
        else:
            shade += .08*np.sqrt(np.clip(1-dx*dx-dy*dy,0,1))
            texture = grain*1.5
        surface = np.clip(palette*shade[...,None]+texture[...,None],4,251).astype(np.uint8)
        image[mask != 0] = surface[mask != 0]
    return image


def encode_reference(image):
    return png_bytes(image)


def validate_collection(plan):
    if (plan.get('schema_version') != 1 or plan.get('kind') != 'natural_material_collection_plan_v1'
            or plan.get('max_requests') != 24 or plan.get('reference_domain') != 'authored_srgb_still_life'
            or len(plan.get('cases', [])) != 24 or len(plan.get('scenes', [])) != 8):
        raise ValueError('exact preregistered acquisition budget required')
    if len({s['reference']['sha256'] for s in plan['scenes']}) != 8:
        raise ValueError('independent reference identities required')
    expected = []
    for i, scene in enumerate(plan['scenes']):
        split = 'development' if i < 4 else 'holdout'
        group = f'g{i+1:02d}_{SCENES[i]}'
        if scene['scene_group'] != group or scene['split'] != split:
            raise ValueError('scene family split differs')
        for seed_index in range(3):
            expected.append(dict(case_id=f'{group}_s{seed_index+1:02d}', scene_group=group, split=split,
                reference=scene['reference'], conversion=scene['conversion'],
                frames=49, fps='16/1', width=768, height=432,
                seed_high=627280000000000+i*100+seed_index, seed_low=0,
                positive_prompt=PROMPT, natural_label='unverified'))
    if plan['cases'] != expected:
        raise ValueError('case identity/group/split/seed/budget/unknown label differs')
    return plan


def freeze_collection(root, config_path):
    root = local(root, exists=False)
    if root == COLLECTION_ROOT or not root.is_relative_to(COLLECTION_ROOT):
        raise ValueError('independent qualification collection root required')
    if root.exists():
        raise FileExistsError('new collection directory required')
    config = load_config(Path(config_path))
    raw = json.loads(Path(config_path).read_text(encoding='utf-8-sig'))
    if raw.get('production_strategy') != 'paragraph_jimeng_v1':
        raise ValueError('direct Wan acquisition requires paragraph_jimeng_v1 configuration')
    for key in ('runtime_root','project_root','output_root','cache_root'):
        raw[key] = str(getattr(config,key))
    raw['voice_config'] = str(config.voice.config_file)
    for key in ('tools','models','workflows'):
        raw[key] = {k:str(v) for k,v in getattr(config,key).items()}
    for key in ('font_file','music'):
        value = getattr(config.media,key)
        if value is not None:
            raw['media'][key] = str(value)
    raw['scene_continuity'] = dict(schema_version=1, policy='advisory_v1')
    root.mkdir(parents=True)
    config_ref = write_json(root/'generation-config.json', raw)
    # Validate actual relocation, not just the original configuration.
    load_config(Path(config_ref['path']))
    renderer_copy = root/'authored-reference-renderer.py'
    with renderer_copy.open('xb') as stream:
        stream.write(Path(__file__).read_bytes())
    renderer_ref = identity(renderer_copy)
    scenes, cases = [], []
    for i, name in enumerate(SCENES):
        folder = root/'references'/f'g{i+1:02d}_{name}'
        folder.mkdir(parents=True)
        path = folder/'selected-reference-srgb.png'
        with path.open('xb') as stream:
            stream.write(encode_reference(render_reference(i)))
        reference = identity(path)
        conversion = write_json(folder/'reference-conversion.json', dict(created_at=now(), target=reference,
            source_kind='authored_srgb_render_v1', source=renderer_ref, scene_index=i,
            operation='Direct authorship in declared sRGB RGB8 code values; no unknown input pixels, no color injection.',
            target_color_intent='Preserve this authored reference material palette and constant illumination.',
            limitation='Computer-rendered still-life reference; not a photograph or observed video label.'))
        split = 'development' if i < 4 else 'holdout'
        group = f'g{i+1:02d}_{name}'
        scenes.append(dict(scene_group=group, split=split, reference=reference, conversion=conversion))
        for j in range(3):
            cases.append(dict(case_id=f'{group}_s{j+1:02d}',scene_group=group,split=split,
                reference=reference,conversion=conversion,frames=49,fps='16/1',width=768,height=432,
                seed_high=627280000000000+i*100+j,seed_low=0,positive_prompt=PROMPT,natural_label='unverified'))
    models = []
    for name in ('wan_high', 'wan_low', 'text_encoder', 'vae'):
        path = config.models[name]
        stat = path.stat()
        models.append(dict(role=name,path=str(path),bytes=stat.st_size,mtime_ns=stat.st_mtime_ns))
    # Bound small executable inputs by bytes, and large shared model resources by existing stamp policy.
    software = [identity(p) for p in sorted(Path(__file__).parent.glob('natural_acquisition*.py'))]
    cli = Path(__file__).parents[3]/'scripts/experiments/vco06_acquire.py'
    if cli.is_file():
        software.append(identity(cli))
    dependencies = [renderer_ref, *[identity(config.workflows[k]) for k in ('wan', 'wan_mapping')]]
    controls = dict(space='linear_srgb',quantization='standard sRGB encode, np.rint uint8, clip [0,1]',
        axes=dict(exposure=[1,1,1],wb_r=[1,-.5,-.5],wb_g=[-.5,1,-.5]),
        constant_levels=[-.01,.01,-.02,.02],identity_amplitude=0,
        known_inverse='multiply original linearRGB by 2**(a*d), then inverse -a; record both quantizations',
        wrong_direction='apply correction with same sign as injection, amplitude abs(a)',
        overcorrection='apply -3*a to injection',mixed_axis='exposure +0.02 and wb_r +0.02',
        temporal='a[i]=0.02*sin(2*pi*i/48), i=0..48',
        local='wb_r +0.02 only in normalized rectangle [0.25,0.25,0.75,0.75]',
        clipping='exposure +2.0 then clamp',structure='shift central rectangle [0.25,0.25,0.75,0.75] right 16px',
        constructed=False,natural_positive=False)
    plan = dict(schema_version=1,kind='natural_material_collection_plan_v1',created_at=now(),max_requests=24,
        reference_domain='authored_srgb_still_life',config=config_ref,scenes=scenes,cases=cases,
        models=models,software=software,dependencies=dependencies,controls=controls,
        seen_exclusions=['old24/all historic holdout','existing paper/cloth material','all previous generated outputs'],
        production_eligible=False,qualification='awaiting_natural_observations',
        retry_policy='No new POST for an existing intent; no replacement cases or source/seed changes.')
    validate_collection(plan)
    frozen = write_json(root/'collection.FROZEN.json', plan)
    write_json(root/'collection-receipt.json',dict(collection=frozen))
    return plan


def load_collection(root):
    root = local(root, exists=False)
    if not root.is_dir():
        raise ValueError('collection directory unavailable')
    if root == COLLECTION_ROOT or not root.is_relative_to(COLLECTION_ROOT):
        raise ValueError('independent qualification collection root required')
    receipt = read_json(root/'collection-receipt.json')
    if Path(receipt['collection']['path']) != root/'collection.FROZEN.json':
        raise ValueError('foreign collection identity')
    plan = validate_collection(read_json(verify(receipt['collection'])))
    for value in [plan['config'], *plan['software'], *plan['dependencies']]:
        verify(value)
    for scene in plan['scenes']:
        verify(scene['reference'])
        verify(scene['conversion'])
    for model in plan['models']:
        path = Path(model['path'])
        stat = path.stat()
        if path != path.resolve(strict=True) or stat.st_size != model['bytes'] or stat.st_mtime_ns != model['mtime_ns']:
            raise ValueError('frozen model stamp identity differs')
    return plan
