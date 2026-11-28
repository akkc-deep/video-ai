"""Explicit installation transactions; never migrate or inspect historical work."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
from uuid import uuid4

from ..config import read_json
from ..runtime.storage_files import safe_path, write_record


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def approved_recipe(source):
    return read_json(Path(source)/'config/approved-narration.json')


def checked_recipe(root, source):
    recipe = read_json(Path(root)/'shared/config/tts/default-narration.json')
    approved = approved_recipe(source)
    keys = set(approved['recipe_identity_fields']) | {'recipe_sha256', 'approved_revision'}
    if any(recipe.get(k) != approved.get(k) for k in keys):
        raise ValueError('default narration differs from approved production recipe; deploy it explicitly first')
    from .voices import load_voice_asset
    asset = load_voice_asset(recipe['voice_profile'], root)
    if (asset.voice_id != approved['voice_id'] or asset.reference_sha256 != approved['reference_sha256']
            or digest(asset.reference_audio) != approved['reference_sha256']):
        raise ValueError('approved voice reference identity differs')
    return recipe


def backup_bytes(path):
    path = Path(path)
    backup = path.with_name(path.stem+'.before-vox10-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid4().hex[:8]+path.suffix)
    with backup.open('xb') as file:
        file.write(path.read_bytes()); file.flush(); os.fsync(file.fileno())
    return backup


def provision_voice(root, source, voice_assets=None):
    root = Path(root).absolute()
    recipe = approved_recipe(source)
    target = safe_path(root/Path(recipe['voice_profile']).parent, root)
    assets = Path(voice_assets).absolute() if voice_assets else target
    from .voices import load_voice_asset
    asset = load_voice_asset(assets/'voice.json', assets)
    if (asset.voice_id != recipe['voice_id'] or asset.reference_sha256 != recipe['reference_sha256']
            or digest(asset.reference_audio) != recipe['reference_sha256']):
        raise ValueError('approved voice source identity differs')
    files = {'voice.json': assets/'voice.json', 'reference.wav': asset.reference_audio,
             Path(recipe['sample']).name: assets/Path(recipe['sample']).name}
    # Validate the entire small asset set before writing any default or asset.
    for name, origin in files.items():
        safe_path(origin, assets)
        if not origin.is_file() or not origin.stat().st_size:
            raise ValueError('missing approved asset: '+str(origin))
        destination = safe_path(target/name, root)
        if destination.exists() and destination.read_bytes() != origin.read_bytes():
            raise ValueError('approved voice asset conflict: '+str(destination))
    target.mkdir(parents=True, exist_ok=True)
    for name, origin in files.items():
        destination = target/name
        if not destination.exists():
            with destination.open('xb') as file: file.write(origin.read_bytes())
    default = safe_path(root/'shared/config/tts/default-narration.json', root)
    if not default.exists() or read_json(default) != recipe:
        if default.exists(): backup_bytes(default)
        write_record(default, recipe)
    return checked_recipe(root, source)


def validate_configuration(path, raw):
    from ..config import load_config
    from ..runtime.production_inputs import validate_supported
    validate_supported(load_config(Path(path), raw=raw))


def activate(config, root, source, *, verified=False):
    config, root = Path(config).absolute(), Path(root).absolute()
    safe_path(config, root/'shared/config')
    recipe = checked_recipe(root, source)
    raw = read_json(config)
    effective = dict(raw, tts=dict(engine='voxcpm2',model_revision=recipe['model_revision'],narration=recipe),
                     services=dict(raw['services'],tts='http://127.0.0.1:9881'))
    validate_configuration(config, effective)
    if effective == raw: return None
    if not verified: verify_installation(root,source,config)
    backup = backup_bytes(config)
    write_record(config, effective)
    return backup


def publish_configuration(candidate, config, root, source):
    """Publish a validated install candidate only after dependency verification."""
    candidate, config, root=Path(candidate).absolute(),Path(config).absolute(),Path(root).absolute()
    safe_path(candidate,root/'shared/config');safe_path(config,root/'shared/config')
    raw=read_json(candidate);recipe=checked_recipe(root,source)
    if raw.get('tts') != dict(engine='voxcpm2',model_revision=recipe['model_revision'],narration=recipe):
        raise ValueError('installation candidate does not use approved narration')
    validate_configuration(config,raw)
    if config.exists():
        if read_json(config)==raw:return None
        backup=backup_bytes(config)
    else:backup=None
    write_record(config,raw)
    return backup


def restore_backup(config, backup):
    config, backup = Path(config).absolute(), Path(backup).absolute()
    safe_path(config, config.parent); safe_path(backup, config.parent)
    if backup == config or backup.suffix != '.json' or '.before-vox' not in backup.name:
        raise ValueError('choose an explicit same-directory configuration backup')
    data = backup.read_bytes()
    raw = json.loads(data.decode('utf-8-sig'))
    validate_configuration(config, raw)
    if config.read_bytes() == data: return None
    previous = backup_bytes(config)
    temporary = config.with_name('.'+config.name+'.'+uuid4().hex+'.tmp')
    try:
        with temporary.open('xb') as file:
            file.write(data); file.flush(); os.fsync(file.fileno())
        os.replace(temporary, config)
    finally:
        temporary.unlink(missing_ok=True)
    return previous


def relocate(root, source, config):
    """Relocate shared dependency paths only; leave provenance and all work untouched."""
    root, source, config = Path(root).absolute(), Path(source).absolute(), Path(config).absolute()
    safe_path(config, root/'shared/config')
    old = read_json(config)['runtime_root'].replace('\\','/').rstrip('/')
    path_keys = {'runtime_root','project_root','output_root','cache_root','voice_config','voice_profile',
                 'reference_audio','gpt_weights','sovits_weights','bert_root','hubert_root','font_file',
                 'sample','original_voice_sample'}
    def updated(value, parent=''):
        if isinstance(value, dict):
            return {k: updated(v,k) if not (parent in {'tools','models','workflows'}) else path(v,parent)
                    for k,v in value.items()}
        if isinstance(value, list): return value
        return path(value,parent) if parent in path_keys else value
    def path(value, key):
        if not isinstance(value,str): return value
        normalized = value.replace('\\','/')
        if key == 'workflows':
            target=source/'workflows'/Path(normalized).name
            return value if Path(value)==target else str(target)
        if old.casefold()==str(root).replace('\\','/').casefold(): return value
        if normalized.casefold() == old.casefold(): return str(root)
        if normalized.casefold().startswith(old.casefold()+'/'):
            return str(root/normalized[len(old)+1:])
        return value
    main=updated(read_json(config))
    # Publish the main root last: an interrupted retry still knows the old root
    # until every dependent shared record has been relocated.
    files=[root/'shared/config/tts/default-narration.json']
    if main.get('voice_config'): files.append(Path(main['voice_config']))
    files.append(config)
    for file in files:
        if not file.exists(): continue
        safe_path(file,root/'shared/config')
        raw=read_json(file); effective=updated(raw)
        if raw != effective:
            backup_bytes(file); write_record(file,effective)
    venv = safe_path(root/'shared/envs/voxcpm2/pyvenv.cfg', root)
    if venv.exists():
        lines = [line for line in venv.read_text(encoding='utf-8-sig').splitlines()
                 if line.split('=',1)[0].strip() not in {'home','executable','command'}]
        base=root/'shared/tools/python312'
        lines += ['home = '+str(base), 'executable = '+str(base/'python.exe')]
        venv.write_text('\n'.join(lines)+'\n',encoding='utf-8')


def verify_installation(root, source, config, *, hash_models=False):
    root, source, config = Path(root).absolute(), Path(source).absolute(), Path(config).absolute()
    recipe = checked_recipe(root, source)
    spec = read_json(source/'config/voxcpm2-deployment.json')
    from .source_identity import source_revision
    actual = source_revision(root/'shared/tools/VoxCPM')
    if actual != spec['source_revision']: raise ValueError('VoxCPM source revision differs')
    for filename, expected in spec['model_files'].items():
        file=root/'shared/models/VoxCPM2'/filename
        if not file.is_file() or not file.stat().st_size: raise ValueError('missing Vox model: '+str(file))
        if hash_models and digest(file)!=expected: raise ValueError('Vox model identity differs: '+filename)
    alignment=read_json(source/'config/voxcpm2-alignment.json')
    for filename, expected in alignment['files'].items():
        file=root/'shared/models/funasr/timestamp'/filename
        if not file.is_file() or not file.stat().st_size: raise ValueError('missing timestamp model: '+str(file))
        if hash_models and digest(file)!=expected: raise ValueError('timestamp model identity differs: '+filename)
    env=dict(os.environ,VIDEO_AI_RUNTIME_ROOT=str(root),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',PYTHONUTF8='1')
    commands = [
        (root/'shared/envs/voxcpm2/Scripts/python.exe',
         "import sys,torch,torchaudio,voxcpm,soundfile; from importlib.metadata import version; "
         "assert sys.version_info[:2]==(3,12); assert torch.__version__=='2.9.1+cu128'; "
         "assert torchaudio.__version__=='2.9.1+cu128'; assert torch.cuda.is_available() and torch.cuda.is_bf16_supported(); "
         "assert version('voxcpm')=='2.0.3.post46+g300e4260b'; print('VoxCPM2 CUDA BF16 imports: ready')"),
        (root/'shared/tools/GPT-SoVITS/runtime/python.exe',
         "from funasr import AutoModel; from importlib.metadata import version; assert version('funasr')=='1.0.27'; print('FunASR CPU alignment imports: ready')")]
    for executable,code in commands:
        subprocess.run([str(executable),'-B','-c',code],env=env,check=True,timeout=120)
    validate_configuration(config, read_json(config))
    return dict(task_id='TTS-VOX-10',status='ready',runtime_root=str(root),voice_id=recipe['voice_id'],
                recipe_sha256=recipe['recipe_sha256'],model_revision=spec['model_revision'],
                source_revision=actual,model_hashes_verified=hash_models,inference_verified=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['provision','activate','restore','relocate','verify'])
    parser.add_argument('--runtime-root',type=Path,default=Path(os.environ.get('VIDEO_AI_RUNTIME_ROOT','E:/VideoAI')))
    parser.add_argument('--source-root',type=Path,default=Path(__file__).resolve().parents[3])
    parser.add_argument('--config',type=Path)
    parser.add_argument('--voice-assets',type=Path)
    parser.add_argument('--backup',type=Path)
    parser.add_argument('--hash-models',action='store_true')
    parser.add_argument('--activate',action='store_true',help='Activate only after verification succeeds')
    parser.add_argument('--publish-to',type=Path,help='Publish verified install candidate to this shared config')
    args=parser.parse_args();config=args.config or args.runtime_root/'shared/config/production.json'
    if args.action=='provision': provision_voice(args.runtime_root,args.source_root,args.voice_assets)
    elif args.action=='activate': print('Backup:',activate(config,args.runtime_root,args.source_root))
    elif args.action=='restore':
        if not args.backup: parser.error('restore requires --backup')
        print('Backup:',restore_backup(config,args.backup))
    elif args.action=='relocate': relocate(args.runtime_root,args.source_root,config)
    else:
        result=verify_installation(args.runtime_root,args.source_root,config,hash_models=args.hash_models)
        if args.activate: print('Backup:',activate(config,args.runtime_root,args.source_root,verified=True))
        if args.publish_to: print('Backup:',publish_configuration(config,args.publish_to,args.runtime_root,args.source_root))
        write_record(args.runtime_root/'shared/config/tts/vox10-install.json',result)
        print(json.dumps(result))


if __name__=='__main__': main()
