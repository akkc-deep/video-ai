"""Run-local Vox recipe and reference assets; global preferences are never read on resume."""
from pathlib import Path

from ..config import read_json
from ..voxcpm.voices import load_voice_asset
from .manifest import hash_file, thaw
from .paths import RuntimePaths
from .production_state import ProductionRefused, json_bytes


def freeze_vox_assets(config, run, identities):
    from .production_inputs import _copy_small, _save_bytes
    recipe = thaw(config.tts.narration)
    root = RuntimePaths.from_config(config).runtime_root
    asset = load_voice_asset(recipe['voice_profile'], root)
    if asset.voice_id != recipe['voice_id'] or asset.reference_sha256 != recipe['reference_sha256']:
        raise ProductionRefused('Vox recipe/reference identity differs')
    folder = run/'production/inputs/vox'
    original, copied = _copy_small(asset.reference_audio, folder/'reference.wav')
    if original.sha256 != recipe['reference_sha256']: raise ProductionRefused('Vox reference SHA256 differs')
    identities['vox_reference'] = thaw(copied)
    _save_bytes(folder/'voice.json', json_bytes(dict(schema_version=1, voice_id=asset.voice_id,
        reference_audio='reference.wav', reference_sha256=asset.reference_sha256, base_style=asset.base_style)))
    _save_bytes(folder/'recipe.json', json_bytes(recipe))
    identities['vox_profile'] = thaw(hash_file(folder/'voice.json'))
    identities['vox_recipe'] = thaw(hash_file(folder/'recipe.json'))


def validate_vox_assets(config, run, records):
    folder = run/'production/inputs/vox'
    for role, name in [('vox_recipe','recipe.json'),('vox_profile','voice.json'),('vox_reference','reference.wav')]:
        if records[role]['path'] != str(folder/name): raise ProductionRefused('Vox frozen asset path differs')
    if read_json(folder/'recipe.json') != thaw(config.tts.narration): raise ProductionRefused('Vox frozen recipe differs')
    asset = load_voice_asset(folder/'voice.json', RuntimePaths.from_config(config).runtime_root)
    if asset.reference_sha256 != config.tts.narration['reference_sha256'] or asset.voice_id != config.tts.narration['voice_id']:
        raise ProductionRefused('Vox frozen voice differs')
