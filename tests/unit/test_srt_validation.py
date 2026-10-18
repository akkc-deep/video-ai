from copy import deepcopy
import pytest
from video_ai.media.subtitles import plan_subtitles, srt_text
from video_ai.planning.composition import CompositionSettings
from composition_helpers import inputs


def validate(path, events, total_samples):
    from video_ai.media.srt_validation import validate_srt
    return validate_srt(path, events, total_samples=total_samples)


def fixture(tmp_path):
    timeline, *_ = inputs()
    events = plan_subtitles(timeline,CompositionSettings(),measure=lambda s:len(s)*300)
    path=tmp_path/'actual.srt';path.write_bytes(('1\n00:00:00,000 --> 00:00:01,000\n夜色渐深，\n\n'
        '2\n00:00:01,000 --> 00:00:02,000\n周围渐静。\n\n'
        '3\n00:00:02,000 --> 00:00:03,000\n水面有灯光\n倒影。\n\n').encode('utf-8'))
    return path,events,timeline.total_samples


def test_exact_two_line_original_srt(tmp_path):
    path,events,total=fixture(tmp_path)
    assert any(len(e['layout']['lines'])==2 for e in events)
    assert validate(path,events,total)==dict(events=events,original_text_passed=True,timing_passed=True,serialization_passed=True)


@pytest.mark.parametrize('mutation',[
    lambda b:b'\xef\xbb\xbf'+b, lambda b:b.replace(b'\n',b'\r\n'), lambda b:b[:-1],
    lambda b:b.replace('夜'.encode(),'昼'.encode()),lambda b:b.replace('夜'.encode(),b'&#22812;'),
    lambda b:b.replace(b'1\n',b'2\n',1),lambda b:b.replace(b'00:00:00,000',b'00:00:00,001',1),
    lambda b:b.replace(b' --> ',b'  --> ',1),lambda b:b+b'4\n00:00:03,000 --> 00:00:04,000\nx\n\n',
    lambda b:b.replace('夜'.encode(),b'{\\b1}'+ '夜'.encode()), lambda b:b.replace('夜'.encode(),b' '+ '夜'.encode()),
    lambda b:b.replace(b'00:00:00,000',b'00:99:00,000',1), lambda b:b'\xff'+b])
def test_rejects_changed_serialization_and_original(tmp_path,mutation):
    path,events,total=fixture(tmp_path);path.write_bytes(mutation(path.read_bytes()))
    with pytest.raises(ValueError):validate(path,events,total)


@pytest.mark.parametrize('kind',['span','samples','milliseconds','layout','three_lines','overlap','duplicate','bool','bounds','nan_width'])
def test_rejects_corrupt_expected_event_associations(tmp_path,kind):
    path,events,total=fixture(tmp_path);events=deepcopy(events)
    if kind=='span':events[0]['text_end']+=1
    if kind=='samples':events[0]['start_sample']=1;events[0]['start_ms']=1
    if kind=='milliseconds':events[0]['end_ms']+=1
    if kind=='layout':events[0]['layout']['line_ranges'][0]['end']-=1
    if kind=='three_lines':events[0]['layout']['lines']=['夜','色','渐深，周围渐静。']
    if kind=='overlap':events[1]['start_sample']=0
    if kind=='duplicate':events[1]['unit_id']=events[0]['unit_id']
    if kind=='bool':events[0]['text_start']=False
    if kind=='bounds':total=1
    if kind=='nan_width':events[0]['layout']['line_widths'][0]=float('nan')
    with pytest.raises(ValueError):validate(path,events,total)


@pytest.mark.parametrize('key,value',[('available_width',True),('available_width',1788.0),
    ('line_widths',[1500.0]),('line_widths',[True]),('line_widths',[]),('line_widths',[2000])])
def test_layout_measurements_keep_exact_integer_contract(tmp_path,key,value):
    path,events,total=fixture(tmp_path);events[0]['layout'][key]=value
    with pytest.raises(ValueError):validate(path,events,total)


def test_rejects_more_than_two_hour_digits_even_with_expected_serialization(tmp_path):
    path,events,_=fixture(tmp_path);event=deepcopy(events[0])
    event.update(start_sample=17280000000,end_sample=17280048000,start_ms=360000000,end_ms=360001000,
        start_cs=36000000,end_cs=36000100,start_frame=5760000,end_frame=5760016)
    path.write_bytes(b'1\n100:00:00,000 --> 100:00:01,000\n'+event['text'].encode()+b'\n\n')
    with pytest.raises(ValueError):validate(path,[event],17280048000)


def test_seven_hand_authored_absolute_events_preserve_original_spans(tmp_path):
    path=tmp_path/'seven.srt'
    events=[];blocks=[]
    for i,text in enumerate(['一。','二。','三。','四。','五。','六。','七。']):
        events.append(dict(unit_id=f'speech_{i+1:04d}',text_start=2*i,text_end=2*i+2,text=text,
            start_sample=i*48000,end_sample=(i+1)*48000,start_frame=i*16,end_frame=(i+1)*16,
            start_ms=i*1000,end_ms=(i+1)*1000,start_cs=i*100,end_cs=(i+1)*100,
            layout=dict(lines=[text],line_ranges=[dict(start=0,end=2)],line_widths=[100],available_width=1788)))
        blocks.append(f'{i+1}\n00:00:0{i},000 --> 00:00:0{i+1},000\n{text}\n\n')
    path.write_bytes(''.join(blocks).encode())
    result=validate(path,events,336000)
    assert len(result['events'])==7
    assert result['timing_passed'] is True
