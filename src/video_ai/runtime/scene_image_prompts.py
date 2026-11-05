"""Effective image text from byte-bound user revisions; base plans stay immutable."""
from pathlib import Path
import re

from .production_state import ProductionRefused


def _focused_prompt(frozen,scene):
    original=scene['image_prompt']
    if getattr(frozen.config,'raw',{}).get('scene_planner_transport')!='focused_v1':return original
    if re.search(r'旅行者\s*[12一二]\s*号|Voyager\s*[12]',frozen.script.text,re.IGNORECASE) is None:return original
    style='写实航天科学纪录片摄影，单一连续画面，不拼贴，画面不含文字、数字标注、标签或水印。'
    if (re.search(r'科学家|工程师|研究人员',original)
            and not re.search(r'控制中心|实验室|研究室|会议室',original)):
        return style+'地球上的任务控制中心，研究人员通过屏幕远程观察与操作；屏幕中的太空景象为：'+original
    visible=re.search(r'探测器|飞船|航天器|旅行者\s*[12一二]\s*号|Voyager',original,re.IGNORECASE)
    other_subject=re.search(r'火箭|发射场|控制中心|科学家|工程师|唱片|照片|图像|影像|拍摄的|传回的|计算机|仪器特写',original)
    if not visible or other_subject:return style+original
    # NASA spacecraft overview: https://science.nasa.gov/mission/voyager/spacecraft/
    # Keep positive visible geometry in probe shots; other scene subjects retain
    # their own composition. Explicit revision overrides bypass this renderer.
    geometry=('主体是经典NASA Voyager无人深空飞船：直径3.7米的巨大白色抛物面碟形天线，'
        '碟面占据飞船大部分视觉面积；天线后连接包覆金色隔热毯的紧凑仪器舱。'
        '细长仪器桁架伸出，一根侧向伸杆承载首尾相连的三节黑色圆柱状核电池。'
        '保留本镜头的环境、景别和动作：')
    return style+geometry+original


def effective_image_prompt(frozen, scene):
    from .scene_revision_records import require_scene_revision, _json
    from ..planning.scene_revision import validate_revision_request_fields
    if 'scene_revision' not in frozen.options:
        return _focused_prompt(frozen,scene)
    proof = require_scene_revision(frozen)
    run = Path(frozen.options['script_path']).parent.parent
    request = _json(proof['commit']['request']['path'], root=run/'production/scene-revision')
    overrides = validate_revision_request_fields(request)
    if scene['scene_id'] in overrides:
        if scene['scene_id'] not in proof['invalidation']['dirty']['images']:
            raise ProductionRefused('image prompt override lacks image invalidation')
        return overrides[scene['scene_id']]
    # A fresh layout has new scene identities; only imported plans inherit text.
    if 'plan:all' in proof['imports']:
        origin = proof['source_frozen']
        return effective_image_prompt(origin, scene)
    return _focused_prompt(frozen,scene)
