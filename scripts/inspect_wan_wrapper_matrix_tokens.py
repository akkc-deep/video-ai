"""Read only the existing 4.55MB spiece tensor and tokenize original frozen prompts."""
import argparse
import json
from pathlib import Path
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    environment=Path('E:/VideoAI/scratch/benchmarks/LVA-07-04-environment')
    sys.path.insert(0,str(environment/'ComfyUI'));sys.argv=[__file__,'--cpu']
    from safetensors import safe_open
    from comfy.text_encoders.wan import WanT5Tokenizer
    path='E:/VideoAI/shared/models/comfyui/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors'
    with safe_open(path,framework='pt',device='cpu') as reader:
        keys=[k for k in reader.keys() if k.endswith('spiece_model')]
        if len(keys)!=1:raise ValueError('unique original tokenizer tensor required')
        spiece=reader.get_tensor(keys[0])
    tokenizer=WanT5Tokenizer(tokenizer_data={'spiece_model':spiece})
    values=json.loads(args.input.read_text(encoding='utf-8'));result={}
    for key,fixture in values.items():
        counts={}
        for slot,name in [('prompt_embeds','positive'),('negative_prompt_embeds','negative')]:
            tokens=tokenizer.tokenize_with_weights(fixture[name])
            chunks=tokens['umt5xxl']
            if len(chunks)!=1:raise ValueError('single unscheduled full native context required')
            counts[slot]=len(chunks[0])
        result[key]=counts
    args.output.write_text(json.dumps(dict(tokenizer_bytes=spiece.numel(),expected_tokens=result,
        checkpoint_payload_scope='spiece only, no encoder weights or GPU'),indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()
