"""Map measured token times onto original unit boundaries without interpolated timestamps."""
import math
import re


def normalized(text):
    return ''.join(c.lower() for c in text if c.isalnum())


def alignment_words(text):
    words=re.findall(r'[A-Za-z]+|[\u4e00-\u9fff0-9]',text)
    if normalized(''.join(words)) != normalized(text):
        unsupported=''.join(dict.fromkeys(c for c in text if c.isalnum() and not re.fullmatch(r'[A-Za-z\u4e00-\u9fff0-9]',c)))
        raise ValueError('unsupported local timestamp alignment characters: '+unsupported)
    return words


def measured_cuts(text, spans, aligned, samples):
    tokens, times = aligned['tokens'], aligned['timestamp']
    if not tokens or len(tokens) != len(times) or ''.join(normalized(t) for t in tokens) != normalized(text):
        raise ValueError('alignment tokens do not cover original speech')
    ends, cursor, previous = {}, 0, 0
    for i, (token, pair) in enumerate(zip(tokens,times)):
        if (len(pair) != 2 or any(type(v) not in (int,float) or not math.isfinite(v) for v in pair)
                or not 0 <= pair[0] <= pair[1] or pair[0] < previous or pair[1]*48 > samples+480):
            raise ValueError('alignment has invalid measured times')
        previous = pair[1]
        cursor += len(normalized(token))
        ends[cursor] = i
    cuts = [0]
    for span in spans[:-1]:
        position = len(normalized(text[:span['end']]))
        if position not in ends or ends[position]+1 >= len(times):
            raise ValueError('unit boundary falls inside an aligned token')
        i = ends[position]
        cut = round((times[i][1]+times[i+1][0])*24)
        if not cuts[-1] < cut < samples: raise ValueError('non-increasing measured speech cuts')
        cuts.append(cut)
    return cuts+[samples]
