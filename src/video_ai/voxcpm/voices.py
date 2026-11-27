"""Small explicit Vox voice assets, independent of historical GPT voice settings."""
from dataclasses import dataclass
from pathlib import Path
import re

from ..runtime.storage_files import read_record, safe_path


@dataclass(frozen=True)
class VoiceAsset:
    voice_id: str
    reference_audio: Path
    reference_sha256: str
    base_style: str


def resolve_voice_profile(path, runtime_root):
    root = Path(runtime_root).absolute()
    profile = Path(path)
    if profile.drive and not profile.is_absolute():
        raise ValueError('drive-relative voice profile is not supported')
    return safe_path(profile if profile.is_absolute() else root/profile, root)


def load_voice_asset(path, runtime_root):
    profile = resolve_voice_profile(path, runtime_root)
    value = read_record(profile)
    identity, digest, style = (value.get(k) for k in ('voice_id','reference_sha256','base_style'))
    if (type(value.get('schema_version')) is not int or value['schema_version'] != 1
            or not isinstance(identity, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,95}', identity)
            or not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest)
            or not isinstance(style, str) or not style.strip() or len(style) > 280):
        raise ValueError('invalid Vox voice asset identity, version, digest or style')
    relative = value.get('reference_audio')
    if not isinstance(relative, str) or not relative.strip():
        raise ValueError('voice reference must be a relative asset path')
    relative = Path(relative)
    if relative.is_absolute() or relative.drive or '..' in relative.parts:
        raise ValueError('voice reference must remain inside the voice asset')
    reference = safe_path(profile.parent/relative, profile.parent)
    if not reference.is_file():
        raise ValueError('voice reference is missing')
    return VoiceAsset(identity, reference, digest, style)
