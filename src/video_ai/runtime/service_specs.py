"""New-location service commands; no process starts during construction."""
from pathlib import Path
from types import MappingProxyType
from urllib.parse import urlsplit

from .manifest import validate_run_dir, ManifestStore, thaw
from .paths import PathPolicy, RUNTIME_ROOT
from .services import ServiceSpec


def build_service_specs(config, run_dir, *, model_stage=None, production=False, frozen=None,
                        store=None, tts_yaml_path=None) -> dict[str,ServiceSpec]:
    run = validate_run_dir(run_dir)
    policy = PathPolicy()
    for path in config.tools.values():
        policy.validate_write(path,'tool-env')
    if type(production) is not bool: raise ValueError('production must be boolean')
    if production:
        return _production_service_specs(config,run,policy,frozen,store,tts_yaml_path,model_stage)
    fixed={'ollama':'http://127.0.0.1:11435','comfyui':'http://127.0.0.1:8188','tts':'http://127.0.0.1:9880'}
    revision=None
    if dict(config.services)!=fixed:
        if not (run/'manifest.json').is_file():
            raise ValueError('service binding change requires an author-bound pipeline revision')
        snapshot=ManifestStore.open(run).snapshot()
        resolved=thaw(config);resolved.pop('voice');resolved.pop('raw')
        if resolved!=snapshot['config_snapshot']['resolved'] or thaw(config.raw)!=snapshot['config_snapshot']['raw']:
            raise ValueError('revised service configuration differs from frozen run')
        from ._pipeline_model_admission import revised_files
        revision=revised_files(config,run,{})
        if revision is None:
            raise ValueError('service binding change requires an author-bound pipeline revision')
    model_binding=None
    if model_stage is not None:
        from ._pipeline_model_paths import prepare_or_consume_model_binding
        model_binding=prepare_or_consume_model_binding(config,run,model_stage)
    model_root=model_binding['root'] if model_binding is not None else RUNTIME_ROOT/'models/comfyui'
    bindings={name:(urlsplit(url).hostname,str(urlsplit(url).port)) for name,url in config.services.items()}
    tools=config.tools
    args=[str(tools['comfy_python']),'-B','-s',str(tools['comfy_root']/'main.py'),
          '--listen',bindings['comfyui'][0],'--port',bindings['comfyui'][1],'--models-directory',str(model_root)]
    if model_binding is not None:
        args.append('--disable-all-custom-nodes')
    for name in ('input','output','temp','user'):
        args.extend((f'--{name}-directory',str(policy.validate_write(run/'comfy'/name,'run'))))
    database=policy.validate_write(run/'comfy/user/comfyui.db','run')
    # Explicit URL also disables Comfy's legacy database rename/copy migration.
    args.extend(('--database-url','sqlite:///'+database.as_posix()))
    timeout=config.timeouts['service_start']
    return {
        'comfyui':ServiceSpec('comfyui',config.services['comfyui'],tuple(args),tools['comfy_root'],timeout),
        'tts':ServiceSpec('tts',config.services['tts'],(str(tools['tts_python']),'-B',str(tools['tts_root']/'api_v2.py'),
                         '-a',bindings['tts'][0],'-p',bindings['tts'][1],'-c',str(config.project_root/'config/tts-api.yaml')),tools['tts_root'],timeout),
        'ollama':ServiceSpec('ollama',config.services['ollama'],(str(tools['ollama_executable']),'serve'),
                            tools['ollama_executable'].parent,timeout,{'OLLAMA_HOST':urlsplit(config.services['ollama']).netloc},
                            run if revision is not None else None),
    }


def _production_service_specs(config,run,policy,frozen,store,tts_yaml_path,model_stage):
    """Consume only caller-owned frozen inputs and the production manifest store."""
    from .production_inputs import FrozenInputs, _resolved
    if (not isinstance(frozen,FrozenInputs) or not isinstance(store,ManifestStore)
            or store.run_dir!=run or store.verify_integrity is not False or model_stage is not None):
        raise ValueError('production service specs require frozen inputs and the production store')
    snapshot=store.snapshot()['config_snapshot']
    frozen_snapshot=frozen.options['config_snapshot']
    if (config!=frozen.config or snapshot['raw']!=frozen_snapshot['raw']
            or snapshot['resolved']!=_resolved(frozen.config)[0]
            or dict(config.services)!=frozen_snapshot['resolved']['services']):
        raise ValueError('production service configuration differs from frozen run')
    from ..adapters.common import validate_base_url
    for url in config.services.values(): validate_base_url(url)
    urls=MappingProxyType(dict(config.services));tools=config.tools;timeout=config.timeouts['service_start']
    specs={'ollama':ServiceSpec('ollama',urls['ollama'],(str(tools['ollama_executable']),'serve'),
                tools['ollama_executable'].parent,timeout,{'OLLAMA_HOST':urlsplit(urls['ollama']).netloc},
                production_services=urls)}
    parts=urlsplit(urls['comfyui'])
    args=[str(tools['comfy_python']),'-B','-s',str(tools['comfy_root']/'main.py'),
          '--listen',parts.hostname,'--port',str(parts.port),'--models-directory',str(RUNTIME_ROOT/'models/comfyui')]
    for name in ('input','output','temp','user'):
        directory=policy.validate_write(run/'comfy'/name,'run')
        args.extend((f'--{name}-directory',str(directory)))
    database=policy.validate_write(run/'comfy/user/comfyui.db','run')
    args.extend(('--database-url','sqlite:///'+database.as_posix()))
    specs['comfyui']=ServiceSpec('comfyui',urls['comfyui'],tuple(args),tools['comfy_root'],timeout,production_services=urls)
    if tts_yaml_path is not None:
        runtime=policy.validate_write(tts_yaml_path,'run')
        if (not runtime.is_relative_to(run/'logs/production/services') or not runtime.is_file()
                or runtime.name!='tts-runtime.yaml' or runtime==Path(frozen.options.get('tts_yaml_path',''))):
            raise ValueError('production TTS requires its independent run-local runtime YAML')
        parts=urlsplit(urls['tts'])
        specs['tts']=ServiceSpec('tts',urls['tts'],(str(tools['tts_python']),'-B',str(tools['tts_root']/'api_v2.py'),
                '-a',parts.hostname,'-p',str(parts.port),'-c',str(runtime)),tools['tts_root'],timeout,
                production_services=urls)
    return specs
