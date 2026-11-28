"""Offline CPU timestamp prediction for a batch of already tempo-processed paragraphs."""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from video_ai.media.speech_alignment import alignment_words


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--model', type=Path, required=True)
    args = parser.parse_args()
    os.environ['HF_HUB_OFFLINE'] = os.environ['TRANSFORMERS_OFFLINE'] = '1'
    from funasr import AutoModel
    model = AutoModel(model=str(args.model), device='cpu', disable_update=True, ncpu=4)
    rows = json.loads(args.request.read_text(encoding='utf-8'))['paragraphs']
    output = []
    for row in rows:
        # Chinese and digits are character tokens; Latin words are passed intact.
        words = alignment_words(row['text'])
        result = model.generate(input=(row['audio_path'], ' '.join(words)), data_type=('sound','text'))[0]
        tokens = alignment_words(result['text'])
        if len(tokens) != len(result['timestamp']): raise ValueError('timestamp token count differs')
        output.append(dict(unit_id=row['unit_id'],tokens=tokens,timestamp=result['timestamp']))
    args.output.write_text(json.dumps(dict(paragraphs=output),ensure_ascii=False,allow_nan=False),encoding='utf-8')


if __name__ == '__main__': main()
