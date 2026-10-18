"""Original-character layout and absolute sample-quantized SRT/ASS files."""
import unicodedata

from ..planning.timeline import validate_timeline
from ..runtime.manifest import thaw


def quantize(sample,rate):
    if type(sample) is not int or sample<0 or type(rate) is not int or rate<=0:raise ValueError('integer sample/time rate required')
    return (2*sample*rate+48000)//96000


def layout_text(text,*,measure,width):
    if type(text) is not str or not text or any(ord(c)<32 for c in text):raise ValueError('subtitle must be nonempty printable original text')
    groups=[]
    for i,c in enumerate(text):
        if groups and (unicodedata.combining(c) or c in ('\ufe0f','\ufe0e','\u200d') or text[i-1]=='\u200d'):
            groups[-1][1]=i+1
        else:groups.append([i,i+1])
    ranges=[];a=0;index=0
    while index<len(groups):
        stop=index
        while stop<len(groups) and measure(text[a:groups[stop][1]])<=width:stop+=1
        if stop==index:raise ValueError('single glyph cluster exceeds subtitle width')
        if stop<len(groups) and text[groups[stop][0]] in '，。！？；：、）》】〉”’' and stop-index>1:stop-=1
        end=groups[stop-1][1];ranges.append(dict(start=a,end=end));a=end;index=stop
        if len(ranges)>2:raise ValueError('subtitle exceeds two lines; finer original segmentation required')
    return dict(lines=[text[r['start']:r['end']] for r in ranges],line_ranges=ranges,
        line_widths=[measure(text[r['start']:r['end']]) for r in ranges],available_width=width)


def plan_subtitles(timeline,settings,*,measure):
    validate_timeline(timeline)
    return plan_subtitle_events(timeline.subtitles,settings,measure=measure)


def plan_subtitle_events(events,settings,*,measure):
    """Lay out validated literal events without choosing a timeline contract."""
    result=[];last_ms=last_cs=0
    width=1920-2*(settings.margin+settings.outline)
    for event in events:
        start_ms,end_ms=quantize(event.start_sample,1000),quantize(event.end_sample,1000)
        start_cs,end_cs=quantize(event.start_sample,100),quantize(event.end_sample,100)
        if not last_ms<=start_ms<end_ms or not last_cs<=start_cs<end_cs:raise ValueError('collapsed/overlapping subtitle time')
        item=dict(thaw(event),start_ms=start_ms,end_ms=end_ms,start_cs=start_cs,end_cs=end_cs,
            layout=layout_text(event.text,measure=measure,width=width))
        result.append(item);last_ms=end_ms;last_cs=end_cs
    return result


def _time(value,rate,separator):
    sec,sub=divmod(value,rate);minute,sec=divmod(sec,60);hour,minute=divmod(minute,60)
    return f'{hour:02d}:{minute:02d}:{sec:02d}{separator}{sub:0{3 if rate==1000 else 2}d}'


def srt_text(events):
    return ''.join(f'{i}\n{_time(e["start_ms"],1000,",")} --> {_time(e["end_ms"],1000,",")}\n'+ '\n'.join(e['layout']['lines'])+'\n\n' for i,e in enumerate(events,1))


def ass_literal(text):
    # A zero-width WORD JOINER prevents a following N/n/h/brace from becoming
    # an ASS escape. Empty braces do not work here: libass renders them visibly.
    return ''.join({'\\':'\\\u2060','{':'\\{','}':'\\}',' ':'\\h'}.get(c,c) for c in text)


def decode_ass_literal(text):
    result=[];i=0
    tokens={'\\\u2060':'\\','\\{':'{','\\}':'}','\\h':' '}
    while i<len(text):
        for token,literal in tokens.items():
            if text.startswith(token,i):result.append(literal);i+=len(token);break
        else:result.append(text[i]);i+=1
    return ''.join(result)


def ass_text(events,settings):
    header='[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n'
    header+=f'Style: Default,{settings.font_name},{settings.font_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,{settings.outline},0,2,{settings.margin},{settings.margin},{settings.margin},1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n'
    return header+''.join(f'Dialogue: 0,{_time(e["start_cs"],100,".")},{_time(e["end_cs"],100,".")},Default,,0,0,0,,'+'\\N'.join(ass_literal(line) for line in e['layout']['lines'])+'\n' for e in events)
