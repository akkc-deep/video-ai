"""Deterministic, SHA-bound narration, subtitle and scene frame materialization."""
import os
from pathlib import Path
import shutil
from uuid import uuid4
import wave

from ..media.font_metrics import PrivateFont
from ..media.production_composition import write_production_narration, BLOCK_SAMPLES
from ..media.subtitles import plan_subtitle_events, srt_text, ass_text
from ..planning.composition import CompositionSettings
from ..planning.production_scenes import canonical_digest
from .manifest import now, thaw
from .production_state import ProductionRefused, object_fields, run_path, timestamp
from .scene_clip_records import equal

MATERIALIZED_FIELDS = ('schema_version run_id inputs_sha256 contributions_sha256 sequence narration '
    'subtitle ass font subtitle_events evidence created_at').split()


def copy_bytes(store, source, target):
    store.verify_global(); source_path=store.validate_artifact(source)
    target=run_path(store.run_dir,target)
    with source_path.open('rb') as incoming,target.open('xb') as output:
        shutil.copyfileobj(incoming,output,1024*1024)
        output.flush(); os.fsync(output.fileno())
    store.verify_global(); store.validate_artifact(source)
    actual=store.artifact(target)
    equal({k:actual[k] for k in ('bytes','sha256')},
          {k:source[k] for k in ('bytes','sha256')},'composition byte copy')
    return actual


def subtitle_layout(context):
    settings=CompositionSettings()
    with PrivateFont(context['frozen'].config.media.font_file,settings.font_name,settings.font_size) as font:
        events=plan_subtitle_events(context['timeline'].subtitles,settings,measure=font.measure)
    return settings,events


def narration_layout(context):
    timeline=context['timeline']; store=context['composition_store']
    return dict(samples=timeline.total_frames*3000,speech_samples=timeline.total_speech_samples,
        silence_samples=timeline.total_silence_samples,padding_samples=timeline.video_padding_samples,
        clips=[dict(unit_id=c.unit_id,start_sample=c.start_sample,end_sample=c.end_sample,
                    samples=c.samples,pcm=store.artifact(c.pcm.path)) for c in timeline.clips])


def _wav(path, samples):
    stream=wave.open(str(path),'rb')
    if (stream.getframerate(),stream.getnchannels(),stream.getsampwidth(),stream.getcomptype(),stream.getnframes()) != (48000,1,2,'NONE',samples):
        stream.close(); raise ProductionRefused('original narration PCM format/sample count differs')
    return stream


def verify_pcm(context, narration):
    store=context['composition_store']; timeline=context['timeline']
    path=store.validate_artifact(narration['audio'])
    with _wav(path,timeline.total_frames*3000) as actual:
        cursor=0
        def silence(count):
            while count:
                size=min(count,BLOCK_SAMPLES); data=actual.readframes(size)
                if data!=bytes(size*2): raise ProductionRefused('narration canonical silence is not zero PCM')
                count-=size
        for clip, binding in zip(timeline.clips,narration['clips'],strict=True):
            silence(clip.start_sample-cursor)
            original=store.validate_artifact(binding['pcm'])
            with _wav(original,clip.samples) as source:
                remaining=clip.samples
                while remaining:
                    size=min(remaining,BLOCK_SAMPLES); data=source.readframes(size)
                    if len(data)!=size*2 or actual.readframes(size)!=data:
                        raise ProductionRefused('narration differs from original speech PCM bytes')
                    remaining-=size
            store.validate_artifact(binding['pcm']); cursor=clip.end_sample
        silence(timeline.total_frames*3000-cursor)
        if actual.readframes(1): raise ProductionRefused('narration contains extra samples')
    store.validate_artifact(narration['audio'])


def verify_materialized(context, value):
    store=context['composition_store']; inputs=context['composition_inputs']; contributions=context['contributions']
    object_fields(value,MATERIALIZED_FIELDS,'scene materialized')
    timestamp(value['created_at'])
    equal({k:value[k] for k in ('schema_version','run_id','inputs_sha256','contributions_sha256')},
        dict(schema_version=2,run_id=store.run_dir.name,inputs_sha256=canonical_digest(inputs),
             contributions_sha256=canonical_digest(contributions)),'materialized identities')
    sequence=value['sequence']
    if not isinstance(sequence,list) or len(sequence)!=len(contributions['frames']):
        raise ProductionRefused('materialized sequence coverage differs')
    folder=store.validate_artifact(value['ass']).parent
    if not folder.is_relative_to(store.path('materialized-attempts')) or folder.parent!=store.path('materialized-attempts'):
        raise ProductionRefused('materialized attempt directory differs')
    for index,(image,row) in enumerate(zip(sequence,contributions['frames'],strict=True),1):
        path=store.validate_artifact(image); source=store.validate_artifact(row['image'])
        if path!=folder/'frames'/f'frame_{index:06d}.png': raise ProductionRefused('materialized frame path/order differs')
        equal({k:image[k] for k in ('bytes','sha256')},{k:row['image'][k] for k in ('bytes','sha256')},'materialized frame bytes')
    if set((folder/'frames').iterdir())!={Path(a['path']) for a in sequence}:
        raise ProductionRefused('materialized frame inventory differs')
    settings,events=context['subtitle_settings'],context['subtitle_events']
    equal(value['subtitle_events'],events,'materialized subtitle events')
    for role,text,name in (('subtitle',srt_text(events),'subtitle.srt'),('ass',ass_text(events,settings),'subtitles.ass')):
        path=store.validate_artifact(value[role])
        if path!=folder/name or path.read_bytes()!=text.encode('utf-8'):
            raise ProductionRefused('materialized original subtitle bytes differ')
    path=store.validate_artifact(value['font']); original=store.validate_artifact(inputs['font'])
    if path!=folder/'fonts'/original.name: raise ProductionRefused('materialized font path differs')
    equal({k:value['font'][k] for k in ('bytes','sha256')},{k:inputs['font'][k] for k in ('bytes','sha256')},'materialized frozen font')
    narration=value['narration']
    object_fields(narration,('audio','samples','speech_samples','silence_samples','padding_samples','clips'),'scene narration')
    equal({k:v for k,v in narration.items() if k!='audio'},narration_layout(context),'narration layout')
    if store.validate_artifact(narration['audio'])!=folder/'narration.wav':
        raise ProductionRefused('materialized narration attempt differs')
    verify_pcm(context,narration)
    if not isinstance(value['evidence'],list): raise ProductionRefused('materialized evidence must be list')
    for evidence in value['evidence']: store.validate_artifact(evidence)
    return value


def materialize(context):
    store=context['composition_store']; ready=store.read('materialized-ready.json'); accepted=store.read('materialized.json')
    if accepted is not None:
        if ready is None: raise ProductionRefused('materialized record lacks original ready receipt')
        equal(accepted,ready,'materialized ready commit'); return verify_materialized(context,accepted)
    if ready is None:
        folder=store.path('materialized-attempts')/str(uuid4()); store.verify_global(); folder.mkdir(parents=True)
        (folder/'frames').mkdir(); (folder/'fonts').mkdir()
        sequence=[copy_bytes(store,row['image'],folder/'frames'/f'frame_{i:06d}.png')
                  for i,row in enumerate(context['contributions']['frames'],1)]
        store.verify_global(); write_production_narration(context['timeline'],folder/'narration.wav'); store.verify_global()
        narration=dict(audio=store.artifact(folder/'narration.wav'),**narration_layout(context))
        for name,text in (('subtitle.srt',srt_text(context['subtitle_events'])),
                          ('subtitles.ass',ass_text(context['subtitle_events'],context['subtitle_settings']))):
            store.write_bytes(folder/name,text.encode('utf-8'))
        font=copy_bytes(store,context['composition_inputs']['font'],folder/'fonts'/Path(context['composition_inputs']['font']['path']).name)
        ready=dict(schema_version=2,run_id=store.run_dir.name,inputs_sha256=canonical_digest(context['composition_inputs']),
            contributions_sha256=canonical_digest(context['contributions']),sequence=sequence,narration=narration,
            subtitle=store.artifact(folder/'subtitle.srt'),ass=store.artifact(folder/'subtitles.ass'),font=font,
            subtitle_events=context['subtitle_events'],evidence=[],created_at=now())
        verify_materialized(context,ready); store.verify_global(); store.write('materialized-ready.json',ready)
    verify_materialized(context,ready); store.verify_global(); store.write('materialized.json',ready)
    return ready
