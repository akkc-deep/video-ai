"""Small deterministic fixture_only inputs, never human calibration evidence."""
from copy import deepcopy
import hashlib


def identity(name='fixture', index=0):
    return dict(path=f'D:\\VideoSi\\fixtures\\{name}_{index}.json',bytes=1,mtime_ns=0,
                sha256=hashlib.sha256(f'{name}_{index}'.encode()).hexdigest(),
                verified_at='2026-10-24T00:00:00+00:00')


def texture(width=128, height=96):
    # Stateless integer mixing; plenty of corners without global RNG changes.
    import numpy as np
    yy,xx=np.indices((height,width),dtype=np.uint32)
    v=(xx*374761393+yy*668265263)^((xx*xx+yy)*1274126177)
    v=(v^(v>>13))*1274126177
    gray=((v^(v>>16))%150+50).astype(np.uint8)
    return np.repeat(gray[:,:,None],3,axis=2)


class Provider:
    def __init__(self, images, masks=None):
        self.images=images; self.masks=masks or {}; self.live=set();self.peak=0
    def get(self, frame_id):
        self.live.add(frame_id);self.peak=max(self.peak,len(self.live))
        image=self.images[frame_id]
        if image is None:return None
        return dict(width=image.shape[1],height=image.shape[0],rgb24=image.tobytes(),
                    valid_mask=self.masks.get(frame_id))
    def release(self, frame_id):self.live.discard(frame_id)


def plan(images, kinds=None):
    ids=list(images)
    frames=[dict(frame_id=f,source_record=identity(index=i),source_clip_id='clip_a',
        source_frame_index=i,source_pts=i,source_time_base='1/16',display_pts=i,
        display_time_base='1/16',output_frame_index=i) for i,f in enumerate(ids)]
    region=dict(region_id='subject',role='subject',identity_note='same synthetic object',
                anchors=[dict(frame_id=ids[0],rect=[.05,.05,.95,.95])])
    background=dict(region_id='background',role='background',identity_note='synthetic background',
                anchors=[dict(frame_id=ids[0],rect=[0.,0.,1.,1.])])
    comparisons=[dict(comparison_id=f'pair_{i}',kind=(kinds or {}).get(i,'adjacent'),
        left=ids[i],right=ids[i+1],region_ids=['subject','background']) for i in range(len(ids)-1)]
    return dict(schema_version=1,algorithm='continuity_cv_v1',purpose='ordinary',
        domain=dict(genre='animation',source_kind='animation'),frames=frames,
        clips=[dict(clip_id='clip_a',frames=ids)],references=[],regions=[region,background],
        comparisons=comparisons,context=None,provenance=dict(kind='verified_source',
            input_sha256='a'*64,source_files=[],control_case=None))


def manifest():
    return dict(schema_version=1,algorithm='continuity_cv_v1',scope='clip',scene_id='scene_a',
        domain=dict(genre='animation',source_kind='animation'),timeline=dict(fps_num=16,fps_den=1),
        clips=[dict(clip_id='clip_a',frames=[dict(frame_id='left',record=identity(index=0)),
                                         dict(frame_id='right',record=identity(index=1))])],
        references=[],regions=identity('regions'),context=None,profile=None,
        comparisons=[dict(comparison_id='pair_a',kind='adjacent',left='left',right='right',
                          region_ids=['subject'])])
