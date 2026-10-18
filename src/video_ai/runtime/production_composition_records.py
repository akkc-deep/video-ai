"""Strict automatic composition records without additional media commands."""
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import math

from ..config import read_json
from ..media.subtitles import quantize
from .production_state import (ArtifactStamp, ProductionRefused, object_fields, integer,
    string, run_path, timestamp, json_bytes, _header)

TECHNICAL_CHECKS = ('source_text_coverage', 'audio_samples', 'frame_mapping', 'subtitles', 'final_media')
COMMAND_FIELDS = ('args', 'cwd', 'returncode', 'timed_out', 'stdout_path', 'stderr_path', 'started_at', 'finished_at')
COMPOSITION_FIELDS = ('candidate', 'subtitle', 'frames', 'samples', 'subtitle_events', 'encoding', 'probe')
EVENT_FIELDS = ('unit_id','text_start','text_end','text','start_sample','end_sample','start_frame','end_frame',
                'start_ms','end_ms','start_cs','end_cs','layout')


def local_stamp(value, run):
    stamp = ArtifactStamp.from_dict(value)
    run_path(run, stamp.path)
    return stamp


def command(value, run):
    object_fields(value, COMMAND_FIELDS, 'media command')
    if not isinstance(value['args'], list) or not value['args']:
        raise ProductionRefused('actual command arguments required')
    for arg in value['args']: string(arg, 'command argument')
    for key in ('cwd','stdout_path','stderr_path'): run_path(run, value[key])
    timestamp(value['started_at']); timestamp(value['finished_at'])
    if type(value['returncode']) is not int or value['returncode'] != 0 or value['timed_out'] is not False:
        raise ProductionRefused('successful untimed-out media command required')


def subtitle_events(events, samples):
    if not isinstance(events, list): raise ProductionRefused('subtitle events must be list')
    previous = 0
    for event in events:
        object_fields(event, EVENT_FIELDS, 'subtitle event')
        string(event['unit_id'], 'subtitle unit'); string(event['text'], 'subtitle text')
        for key in EVENT_FIELDS:
            if key not in ('unit_id','text','layout'): integer(event[key], key)
        a,b=event['start_sample'],event['end_sample']
        if not previous <= a < b <= samples or event['text_end']-event['text_start'] != len(event['text']):
            raise ProductionRefused('subtitle sample/text range differs')
        if event['start_frame'] != quantize(a,16) or event['end_frame'] != quantize(b,16):
            raise ProductionRefused('subtitle frame range differs')
        for rate, suffix in ((1000,'ms'),(100,'cs')):
            if (event[f'start_{suffix}'],event[f'end_{suffix}']) != (quantize(a,rate),quantize(b,rate)):
                raise ProductionRefused('subtitle quantization differs')
            if event[f'start_{suffix}'] >= event[f'end_{suffix}']: raise ProductionRefused('subtitle time collapsed')
        layout=event['layout']; object_fields(layout,('lines','line_ranges','line_widths','available_width'),'subtitle layout')
        lines,ranges,widths=layout['lines'],layout['line_ranges'],layout['line_widths']
        if not all(isinstance(x,list) for x in (lines,ranges,widths)) or not 1<=len(lines)<=2 or len(lines)!=len(ranges) or len(lines)!=len(widths):
            raise ProductionRefused('one or two original subtitle lines required')
        available=layout['available_width']
        _number(available,'subtitle available width')
        if available <= 0: raise ProductionRefused('positive subtitle width required')
        cursor=0
        for line,r,width in zip(lines,ranges,widths):
            string(line,'subtitle line');object_fields(r,('start','end'),'subtitle line range')
            integer(r['start'],'line start');integer(r['end'],'line end',1);_number(width,'line width')
            if r['start'] != cursor or r['end'] <= cursor or line != event['text'][cursor:r['end']] or not 0<=width<=available:
                raise ProductionRefused('subtitle original layout differs')
            cursor=r['end']
        if cursor != len(event['text']) or ''.join(lines)!=event['text']: raise ProductionRefused('subtitle text coverage differs')
        previous=b


def _number(value,label):
    if type(value) not in (int,float) or type(value) is float and not math.isfinite(value):
        raise ProductionRefused(f'{label}: finite number required')


def _decimal(value,label):
    if type(value) not in (str,int,float): raise ProductionRefused(f'{label}: numeric value required')
    try: result=Decimal(str(value))
    except InvalidOperation as exc: raise ProductionRefused(f'{label}: invalid number') from exc
    if not result.is_finite(): raise ProductionRefused(f'{label}: finite number required')
    return result


def _allowed(value, fields, label):
    if not isinstance(value,dict) or set(value)-set(fields): raise ProductionRefused(f'{label}: unknown fields')


def probe(value,frames):
    # Preserve the full native ffprobe JSON, including its standard metadata.
    _allowed(value,('streams','format'),'ffprobe')
    streams=value.get('streams')
    if not isinstance(streams,list) or len(streams)!=2: raise ProductionRefused('one video and one audio stream required')
    allowed=('index codec_name codec_long_name profile codec_type codec_tag_string codec_tag mime_codec_string width height coded_width coded_height '
        'closed_captions film_grain has_b_frames sample_aspect_ratio display_aspect_ratio pix_fmt level color_range color_space '
        'color_transfer color_primaries chroma_location field_order refs is_avc nal_length_size id r_frame_rate avg_frame_rate '
        'time_base start_pts start_time duration_ts duration bit_rate bits_per_raw_sample nb_frames nb_read_frames '
        'nb_read_packets extradata_size disposition tags side_data_list sample_fmt sample_rate channels channel_layout '
        'bits_per_sample initial_padding').split()
    by_type={}
    for row in streams:
        _allowed(row,allowed,'ffprobe stream')
        kind=row.get('codec_type')
        if kind not in ('video','audio') or kind in by_type: raise ProductionRefused('unique video/audio streams required')
        by_type[kind]=row
        if _decimal(row.get('start_time'),'stream start')!=0: raise ProductionRefused('media stream must start at zero')
        if 'disposition' in row:
            _allowed(row['disposition'],('default dub original comment lyrics karaoke forced hearing_impaired visual_impaired '
                'clean_effects attached_pic timed_thumbnails non_diegetic captions descriptions metadata dependent still_image multilayer').split(),'stream disposition')
            for flag in row['disposition'].values():
                integer(flag,'stream disposition')
                if flag not in (0,1): raise ProductionRefused('invalid stream disposition')
        if 'tags' in row and not isinstance(row['tags'],dict): raise ProductionRefused('stream tags must be object')
    v,a=by_type['video'],by_type['audio']
    for key in ('width','height'): integer(v.get(key),f'video {key}',1)
    integer(a.get('channels'),'audio channels',1)
    if (v.get('width'),v.get('height'),v.get('codec_name'),v.get('pix_fmt'))!=(1920,1080,'h264','yuv420p'):
        raise ProductionRefused('1080p H264 yuv420p required')
    try:
        for key in ('r_frame_rate','avg_frame_rate'):
            if not isinstance(v.get(key),str) or Fraction(v[key])!=16: raise ValueError()
    except (ValueError,ZeroDivisionError) as exc: raise ProductionRefused('native16 media required') from exc
    if _decimal(v.get('nb_read_frames'),'read frames')!=frames: raise ProductionRefused('final frame count differs')
    if (a.get('codec_name'),_decimal(a.get('sample_rate'),'audio sample rate'),a['channels'])!=('aac',48000,1):
        raise ProductionRefused('AAC48kHz mono required')
    duration=Decimal(frames)/16
    vd,ad=_decimal(v.get('duration'),'video duration'),_decimal(a.get('duration'),'audio duration')
    if abs(vd-duration)>Decimal('0.000001') or abs(vd-ad)>Decimal('0.1'): raise ProductionRefused('final media duration differs')
    fmt=value.get('format');_allowed(fmt,('filename nb_streams nb_programs nb_stream_groups format_name format_long_name start_time duration size bit_rate probe_score tags').split(),'ffprobe format')
    if abs(_decimal(fmt.get('duration'),'format duration')-duration)>Decimal('0.1'): raise ProductionRefused('container duration differs')
    json_bytes(value)


def validate_composition_report(payload, run):
    object_fields(payload,COMPOSITION_FIELDS,'composition payload')
    for key in ('candidate','subtitle'):local_stamp(payload[key],run)
    integer(payload['frames'],'composition frames',1);integer(payload['samples'],'composition samples',1)
    if payload['samples'] != payload['frames']*3000: raise ProductionRefused('full native16 sample count required')
    subtitle_events(payload['subtitle_events'],payload['samples']);command(payload['encoding'],run)
    probe(payload['probe'],payload['frames']);json_bytes(payload)


def narration(value,run,samples):
    object_fields(value,('stamp','samples','speech_samples','silence_samples','padding_samples','clips'),'narration')
    local_stamp(value['stamp'],run)
    for key in ('samples','speech_samples','silence_samples','padding_samples'):integer(value[key],f'narration {key}')
    if value['samples']!=samples or sum(value[k] for k in ('speech_samples','silence_samples','padding_samples'))!=samples or value['padding_samples']>=3000:
        raise ProductionRefused('narration sample totals/padding differ')
    if not isinstance(value['clips'],list) or not value['clips']: raise ProductionRefused('original narration clips required')
    total=cursor=0;ids=set()
    for row in value['clips']:
        object_fields(row,('unit_id','start_sample','end_sample','samples','pcm'),'narration clip')
        string(row['unit_id'],'narration unit');local_stamp(row['pcm'],run)
        for key in ('start_sample','end_sample','samples'):integer(row[key],key)
        if row['unit_id'] in ids or not cursor<=row['start_sample']<row['end_sample']<=samples-value['padding_samples'] or row['end_sample']-row['start_sample']!=row['samples']:
            raise ProductionRefused('original narration clip sequence differs')
        cursor=row['end_sample'];total+=row['samples'];ids.add(row['unit_id'])
    if total!=value['speech_samples']: raise ProductionRefused('original speech sample count differs')


def validate_composition_checkpoint(uid,payload,run):
    if uid=='materialized':
        object_fields(payload,('frames','samples','sequence','narration','subtitle','ass','font','subtitle_events','contributions'),'materialized composition')
        integer(payload['frames'],'frames',1);integer(payload['samples'],'samples',1)
        if payload['samples']!=payload['frames']*3000: raise ProductionRefused('materialized sample count differs')
        sequence=run_path(run,payload['sequence'])
        for key in ('subtitle','ass','font'):local_stamp(payload[key],run)
        narration(payload['narration'],run,payload['samples']);subtitle_events(payload['subtitle_events'],payload['samples'])
        rows=payload['contributions']
        if not isinstance(rows,list) or len(rows)!=payload['frames']: raise ProductionRefused('complete contribution frames required')
        previous_shot=None;previous_index=-1
        from .production_visual_records import _id
        for i,row in enumerate(rows,1):
            object_fields(row,('output_frame_index','shot_id','source_frame_index','upscaled_frame_index','input','output'),'contribution')
            _id(row['shot_id'])
            for key in ('output_frame_index','source_frame_index','upscaled_frame_index'):integer(row[key],key)
            expected=previous_index+1 if previous_shot==row['shot_id'] else 0
            if previous_shot is None and row['shot_id']!='shot_0001':
                raise ProductionRefused('first contribution shot must be shot_0001')
            if row['output_frame_index']!=i-1 or row['source_frame_index']!=expected or row['upscaled_frame_index']!=expected:
                raise ProductionRefused('contribution sequence/mapping differs')
            if previous_shot is not None and previous_shot!=row['shot_id'] and int(row['shot_id'][5:])!=int(previous_shot[5:])+1:
                raise ProductionRefused('contribution shot order differs')
            local_stamp(row['input'],run)
            output=local_stamp(row['output'],run)
            if run_path(run,output.path)!=sequence/f'frame_{i:06d}.png': raise ProductionRefused('contribution filename differs')
            previous_shot,previous_index=row['shot_id'],expected
    elif uid=='encoded':
        object_fields(payload,('candidate','encoding','materialized_checkpoint'),'encoded composition')
        local_stamp(payload['candidate'],run);command(payload['encoding'],run)
        cp=local_stamp(payload['materialized_checkpoint'],run)
        if run_path(run,cp.path)!=run/'logs/production/checkpoints/composition/materialized.json':
            raise ProductionRefused('materialized checkpoint path differs')
    elif uid=='final':validate_composition_report(payload,run)
    else:raise ProductionRefused('unknown composition checkpoint unit')
    json_bytes(payload)


def validate_composition_links(data,run):
    """Bind completed records to the persisted command and checkpoint evidence."""
    uid,payload,outputs=data['unit_id'],data['payload'],data['outputs']
    if uid=='materialized':return
    from .production_state import validate_checkpoint
    def prior(name):
        path=run/f'logs/production/checkpoints/composition/{name}.json'
        stamp=next((s for s in outputs.values() if s['path']==str(path)),None)
        if stamp is None:raise ProductionRefused(f'actual {name} checkpoint output required')
        record=read_json(path);validate_checkpoint(record,run,'composition',name)
        return stamp,record['payload']
    materialized_stamp,materialized=prior('materialized')
    if uid=='encoded':
        if materialized_stamp!=payload['materialized_checkpoint']:
            raise ProductionRefused('encoded materialized checkpoint differs')
    elif uid=='final':
        _,encoded=prior('encoded')
        if (payload['candidate'],payload['encoding'])!=(encoded['candidate'],encoded['encoding']):
            raise ProductionRefused('final candidate/encoding differs from encoded checkpoint')
        if any(payload[key]!=materialized[key] for key in ('subtitle','frames','samples','subtitle_events')):
            raise ProductionRefused('final layout differs from materialized checkpoint')
        stdout=outputs.get('stdout_path')
        stderr=outputs.get('stderr_path')
        if stdout is None or stderr is None:raise ProductionRefused('actual final probe command logs required')
        if read_json(run_path(run,stdout['path']))!=payload['probe']:
            raise ProductionRefused('final probe differs from actual command stdout')


def validate_technical_checks(data,run):
    object_fields(data,('schema_version','execution_mode','run_id','created_at','composition_report','technical_checks','human_review'),'technical checks')
    _header(data,run)
    if data['human_review']!='unverified':raise ProductionRefused('human review must remain unverified')
    object_fields(data['technical_checks'],TECHNICAL_CHECKS,'technical checks statuses')
    if any(v!='passed' for v in data['technical_checks'].values()): raise ProductionRefused('completed composition requires five passed checks')
    report=local_stamp(data['composition_report'],run)
    if run_path(run,report.path)!=run/'production/composition.json': raise ProductionRefused('composition report path differs')
    report.verify()
    from .production_state import validate_report
    validate_report(read_json(run_path(run,report.path)),run,'composition')
    json_bytes(data)
