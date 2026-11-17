"""LVA-04-only immutable identities. No torch, network or production mutation."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

QUALITY_SHA = '5f3768f6e83bf6be21287457c7c15e811d8f6949b7b5c5ac5460c267c8f98666'
REVISION = '57adea585d1d21085e2dfc91ce3c7b646cdd9345'
LORA_PINS = {
    'lora_high': dict(filename='wan2.2_i2v_A14b_high_noise_lora_rank64_lightx2v_4step_1022.safetensors',
        bytes=634645944, sha256='887c3bdeb74e83859c920438e16ca31f39ab18ce189abc5f0e36f8348c5bbb19'),
    'lora_low': dict(filename='wan2.2_i2v_A14b_low_noise_lora_rank64_lightx2v_4step_1022.safetensors',
        bytes=739472104, sha256='8833bd4fd7c8eabebf0bc8ee5cfaf47f4f310ce116928a02c1adf8941dd4b0f1'),
}
BASE_ROLES = frozenset(('wan_high', 'wan_low', 'text_encoder', 'vae', 'workflow', 'mapping',
                        'provenance', 'node_source', 'media_source'))


class UnsupportedProfile(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class Artifact:
    path: str
    bytes: int
    sha256: str

    def __post_init__(self):
        path = Path(self.path)
        if (not path.is_absolute() or '..' in path.parts or type(self.bytes) is not int
                or self.bytes < 0 or not re.fullmatch('[0-9a-f]{64}', self.sha256)):
            raise ValueError('invalid artifact identity')

    def identity_dict(self):
        return dict(path=self.path, bytes=self.bytes, sha256=self.sha256)

    def verify(self):
        # hash_file reuses only real deny-write/delete leases inside an explicit
        # whole_input_protection scope; other platforms strictly rehash.
        from video_ai.runtime.manifest import hash_file
        path = Path(self.path)
        if path.resolve(strict=True) != path or path.is_symlink():
            raise ValueError('artifact path alias')
        actual = hash_file(path)
        if actual.sha256 != self.sha256 or actual.bytes != self.bytes:
            raise ValueError('artifact content drift: '+path.name)


def artifact(path):
    from video_ai.runtime.manifest import hash_file
    value = hash_file(Path(path).resolve(strict=True))
    return Artifact(str(Path(path).resolve()), value.bytes, value.sha256)


@dataclass(frozen=True, slots=True)
class WanFastProfile:
    mode: str
    factor: str
    assets: tuple
    environment_json: str
    steps: int
    cfg: float
    split: int
    shift: float = 5.0
    sampler: str = 'euler'
    scheduler: str = 'simple'
    sigma_points: tuple = ()
    strengths: tuple = ()
    attention_backend: str = 'native'
    cache_backend: str = 'none'
    compile_backend: str = 'none'
    residency_policy: str = 'native'
    schema_version: int = 1

    def identity_dict(self):
        return dict(schema_version=self.schema_version, mode=self.mode, factor=self.factor,
            assets={k: a.identity_dict() for k, a in self.assets}, environment=json.loads(self.environment_json),
            steps=self.steps, cfg=self.cfg, split=self.split, shift=self.shift, sampler=self.sampler,
            scheduler=self.scheduler, sigma_points=list(self.sigma_points), strengths=list(self.strengths),
            attention_backend=self.attention_backend, cache_backend=self.cache_backend,
            compile_backend=self.compile_backend, residency_policy=self.residency_policy,
            checks=dict(finite_image=True, black_channel_max=1, black_pixel_fraction=0.999,
                        black_consecutive_frames=2))

    def digest(self):
        return digest(self.identity_dict())


def load_profile(mode='quality', *, factor='distill', assets, capabilities):
    if mode not in ('quality', 'fast_experimental') or factor not in ('distill', 'sage', 'cache', 'compile', 'combination'):
        raise ValueError('unknown mode/factor')
    if set(capabilities) - {'environment', 'sage', 'triton', 'accepted_factors'}:
        raise ValueError('unknown capability field')
    if capabilities.get('environment') is None or not isinstance(capabilities['environment'], dict) or not capabilities['environment']:
        raise ValueError('explicit environment identity required')
    if factor != 'distill':
        # The current reviewed environment has no supported native dual-expert
        # cache or accepted accelerated factor. Never encode native fallback as
        # an accelerated success. New support requires a separately tested design.
        raise UnsupportedProfile({'sage': 'sageattention capability and accepted distill evidence required',
            'cache': 'no verified native dual-expert cache',
            'compile': 'compatible Triton/inductor and accepted distill evidence required',
            'combination': 'no independently accepted accelerated factors'}[factor])
    roles = BASE_ROLES | ({'lora_high', 'lora_low'} if mode == 'fast_experimental' else set())
    if set(assets) != roles or any(not isinstance(a, Artifact) for a in assets.values()):
        raise ValueError('missing/unknown artifact role')
    for a in assets.values():
        a.verify()
    for entry in capabilities['environment'].get('artifacts', {}).values():
        Artifact(**entry).verify()
    if mode == 'fast_experimental':
        for role, pin in LORA_PINS.items():
            a = assets[role]
            if (Path(a.path).name, a.bytes, a.sha256) != (pin['filename'], pin['bytes'], pin['sha256']):
                raise ValueError('artifact LoRA role/pin differs: '+role)
    elif assets['workflow'].sha256 != QUALITY_SHA:
        raise ValueError('original quality graph SHA differs')
    fast = mode == 'fast_experimental'
    return WanFastProfile(mode, factor, tuple(sorted(assets.items())),
        json.dumps(capabilities['environment'], sort_keys=True, ensure_ascii=False, allow_nan=False),
        4 if fast else 40, 1.0 if fast else 3.5, 2 if fast else 15,
        sigma_points=(1, 15/16, 5/6, 5/8, 0) if fast else (), strengths=(1.0, 1.0) if fast else ())


def write_once(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if json.loads(path.read_text(encoding='utf-8')) != value:
            raise ValueError('immutable experiment evidence differs: '+path.name)
        return
    import os
    with path.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2)+'\n')
        stream.flush()
        os.fsync(stream.fileno())


def freeze_profile(root, profile):
    for _, a in profile.assets:
        a.verify()
    write_once(Path(root)/'frozen/profile.json', dict(profile=profile.identity_dict(), profile_sha256=profile.digest()))


def verify_profile(root, expected_digest):
    saved = json.loads((Path(root)/'frozen/profile.json').read_text(encoding='utf-8'))
    value = saved['profile']
    if set(saved) != {'profile', 'profile_sha256'} or saved['profile_sha256'] != expected_digest or digest(value) != expected_digest:
        raise ValueError('profile identity drift')
    assets = {k: Artifact(**a) for k, a in value['assets'].items()}
    profile = load_profile(value['mode'], factor=value['factor'], assets=assets,
                           capabilities={'environment': value['environment']})
    if profile.identity_dict() != value:
        raise ValueError('profile fields/backend drift')
    return profile
