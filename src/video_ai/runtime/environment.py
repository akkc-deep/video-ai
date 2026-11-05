"""Per-child D: environment; never mutate the parent or machine settings."""
import os

from .paths import RuntimePaths, CACHE_ROOT

CACHE_LOCATIONS = {
    'TEMP': 'temp', 'TMP': 'temp', 'TMPDIR': 'temp',
    'PYTHONPYCACHEPREFIX': 'pycache', 'HF_HOME': 'huggingface',
    'HF_HUB_CACHE': 'huggingface/hub', 'TRANSFORMERS_CACHE': 'huggingface/transformers',
    'TORCH_HOME': 'torch', 'PIP_CACHE_DIR': 'pip', 'UV_CACHE_DIR': 'uv',
    'UV_PYTHON_INSTALL_DIR': 'uv-python', 'XDG_CACHE_HOME': 'xdg',
    'CUDA_CACHE_PATH': 'cuda', 'TORCHINDUCTOR_CACHE_DIR': 'torchinductor',
    'TRITON_CACHE_DIR': 'triton', 'MPLCONFIGDIR': 'matplotlib',
    'NUMBA_CACHE_DIR': 'numba', 'NLTK_DATA': 'nltk',
}


def build_child_env(paths: RuntimePaths) -> dict[str, str]:
    paths.validate()
    policy = paths.policy
    from .storage import test_root_for_paths
    test_root = test_root_for_paths(paths)
    runtime = test_root or paths.runtime_root
    disposable = runtime/'disposable/video-ai'
    dependencies = {
        'HF_HOME': ('huggingface','models/huggingface','model'),
        'HF_HUB_CACHE': ('huggingface/hub','models/huggingface/hub','model'),
        'TRANSFORMERS_CACHE': ('huggingface/transformers','models/huggingface/transformers','model'),
        'TORCH_HOME': ('torch','models/torch','model'),
        'UV_PYTHON_INSTALL_DIR': ('uv-python','envs/python','tool-env'),
        'NLTK_DATA': ('nltk','models/nltk','model'),
    }
    targets = {}
    for key,relative in CACHE_LOCATIONS.items():
        if key in dependencies:
            old,new,category = dependencies[key]
            legacy = (runtime/'cache/video-ai' if test_root else CACHE_ROOT)/old
            target = legacy if legacy.exists() else runtime/new
            targets[key] = policy.validate_write(target,'cache' if target==legacy else category)
        else:
            target = disposable/'tmp' if key in ('TEMP','TMP','TMPDIR') else disposable/'cache'/relative
            targets[key] = policy.validate_write(target,'cache')
    targets['OLLAMA_MODELS'] = policy.validate_write(runtime/'models/ollama', 'model')
    # Validate the complete plan before creating any directory.
    for path in set(targets.values()):
        path.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update({key: str(path) for key, path in targets.items()})
    env['PYTHONUTF8'] = '1'
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['PIP_DISABLE_PIP_VERSION_CHECK'] = '1'
    env['HF_HUB_OFFLINE'] = '1'
    env['TRANSFORMERS_OFFLINE'] = '1'
    return env
