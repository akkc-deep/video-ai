"""Source-identified CPU diagnosis of the original merged traversal; not a fix."""
import argparse
import ast
import collections
import hashlib
import importlib.util
import json
from pathlib import Path
import time
import types


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    import torch
    from tqdm import tqdm
    assert str(torch.__version__)=='2.14.1+cpu' and torch.version.cuda is None
    repo=Path(__file__).resolve().parents[1]
    spec=importlib.util.spec_from_file_location('lva07_components',repo/'scripts/validate_lva07_applicable_payloads.py');component=importlib.util.module_from_spec(spec);spec.loader.exec_module(component)
    comfy=Path('E:/VideoAI/shared/tools/ComfyUI_windows_portable/ComfyUI')
    ns,records=component.components(comfy,repo/'docs/task-designs/LVA-07-environment-review.json')
    def extract(path,names):
        raw=path.read_bytes();tree=ast.parse(raw)
        nodes=[n for n in tree.body if (isinstance(n,(ast.ClassDef,ast.FunctionDef)) and n.name in names) or (isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in names for t in n.targets))]
        found={n.name for n in nodes if isinstance(n,(ast.ClassDef,ast.FunctionDef))}|{t.id for n in nodes if isinstance(n,ast.Assign) for t in n.targets if isinstance(t,ast.Name)}
        assert found==set(names)
        exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),ns)
        records.append({'path':str(path),'sha256':hashlib.sha256(raw).hexdigest(),'symbols':names})
    ns.update(args=types.SimpleNamespace(force_non_blocking=True),PROGRESS_BAR_HOOK=None,time=time,types=types,collections=collections,tqdm=tqdm)
    extract(comfy/'comfy/utils.py',['ATTR_UNSET','get_attr','resolve_attr','set_attr','set_attr_param','copy_to_param','string_to_seed','ProgressBar'])
    utils=types.SimpleNamespace(**{n:ns[n] for n in ['get_attr','set_attr','set_attr_param','copy_to_param']})
    extract(comfy/'comfy/model_management.py',['cast_to','cast_to_device','device_supports_non_blocking'])
    mm=types.SimpleNamespace(**{n:ns[n] for n in ['cast_to','cast_to_device']})
    ns['comfy']=types.SimpleNamespace(utils=utils,model_management=mm);ns['mm']=mm
    extract(comfy/'comfy/model_patcher.py',['get_key_weight'])
    extract(comfy/'comfy/float.py',['stochastic_rounding'])
    extract(comfy/'comfy/lora.py',['calculate_weight'])
    extract(Path('E:/VideoAI/scratch/benchmarks/LVA-07-01-source-audit/utils.py'),['patch_weight_to_device','apply_lora','set_module_tensor_to_device'])
    root=torch.nn.Module();transformer=torch.nn.Module();block=torch.nn.Module()
    block.modulation=torch.nn.Parameter(torch.ones((1,6,2),dtype=torch.float64));block.linear=torch.nn.Linear(2,2,dtype=torch.float64);block.norm=torch.nn.LayerNorm(2,dtype=torch.float64)
    with torch.no_grad():block.linear.bias.copy_(torch.tensor([.5,-.5],dtype=torch.float64))
    transformer.blocks=torch.nn.ModuleList([block]);transformer.head=torch.nn.Module();transformer.head.modulation=torch.nn.Parameter(torch.ones((1,2,2),dtype=torch.float64));transformer.head.linear=torch.nn.Linear(2,2,dtype=torch.float64)
    root.diffusion_model=transformer
    patch=lambda x:[(.5,('diff',(x,)),1.,None,None)]
    patches={'diffusion_model.blocks.0.modulation':patch(torch.full((1,6,2),.25)),'diffusion_model.head.modulation':patch(torch.full((1,2,2),.25)),'diffusion_model.blocks.0.linear.bias':patch(torch.tensor([.25,-.75])),'diffusion_model.blocks.0.norm.weight':patch(torch.full((2,),.25))}
    model=types.SimpleNamespace(model=root,patches=patches,weight_inplace_update=False,backup={},offload_device=torch.device('cpu'),patches_uuid='fixture')
    ns['apply_lora'](model,None,None,scale_weights={})
    actual_block=transformer.blocks[0].modulation.detach();actual_head=transformer.head.modulation.detach()
    assert torch.equal(actual_block,torch.ones_like(actual_block)) and torch.equal(actual_head,torch.ones_like(actual_head))
    torch.testing.assert_close(transformer.blocks[0].linear.bias,torch.tensor([.625,-.875],dtype=torch.float64))
    torch.testing.assert_close(transformer.blocks[0].norm.weight,torch.full((2,),1.125,dtype=torch.float64))
    result={'diagnosis_passed':True,'merged_supported':False,'actual_original_function_executed':True,'block_modulation_expected':1.125,'block_modulation_actual':1.,'head_modulation_expected':1.125,'head_modulation_actual':1.,'linear_bias_actual':transformer.blocks[0].linear.bias.detach().tolist(),'norm_weight_actual':transformer.blocks[0].norm.weight.detach().tolist(),'source_components':records,'scope':'Original merged AST function bodies on CPU/low_mem_load=False/scale_weights empty. Namespace config force_non_blocking=True, real cast functions, no full Comfy registration. Reproduced nonleaf modulation skip, not compatibility success.','full_model_verified':False,'gpu_calls':0}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_bytes((json.dumps(result,indent=2)+'\n').encode());print(json.dumps({k:v for k,v in result.items() if k!='source_components'}));return 0


if __name__=='__main__':raise SystemExit(main())
