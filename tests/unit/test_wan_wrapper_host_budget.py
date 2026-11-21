import importlib.util
import math
from pathlib import Path
import sys
import types

import pytest

from video_ai.experiments.wan_wrapper_backend import contract
from video_ai.experiments.wan_wrapper_nodes import WorkerContext


def controller_module():
    path = Path(__file__).resolve().parents[2] / 'scripts/observe_wan_wrapper_comfy.py'
    spec = importlib.util.spec_from_file_location('host_budget_controller', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_host_minima_preserve_runtime_hard_caps():
    limits = contract()['future_full_model_limits']
    assert limits['min_available_ram_bytes'] == 14 * 1024**3
    assert limits['min_free_vram_bytes'] == 21 * 1024**3
    assert limits['process_private_commit_bytes'] == 18 * 1024**3
    assert limits['min_available_commit_bytes'] == 26 * 1024**3
    assert limits['rss_stop_bytes'] == 24 * 1024**3
    assert limits['torch_gpu_allocator_bytes'] == 20 * 1024**3
    assert limits['max_active_experts'] == 1


def test_no_total_deadline_requires_explicit_gpu_authorization():
    module = controller_module()
    approved = dict(approved=True, user_evidence='时间可以不限制', max_service_seconds=None)
    assert math.isinf(module.execution_deadline_seconds('gpu', 0, approved))
    for mode, auth in [('cpu', approved), ('gpu', None), ('gpu', {}),
                       ('gpu', dict(approved=True, user_evidence='yes', max_service_seconds=14400)),
                       ('gpu', dict(approved=True, user_evidence='yes'))]:
        with pytest.raises(ValueError):
            module.execution_deadline_seconds(mode, 0, auth)
    assert module.execution_deadline_seconds('cpu', 180, None) == 180
    assert module.execution_deadline_seconds('gpu', 14400, None) == 14400
    for mode, seconds in [('cpu', 181), ('gpu', -1), ('gpu', 14401), ('invalid', 180)]:
        with pytest.raises(ValueError):
            module.execution_deadline_seconds(mode, seconds, approved)


@pytest.mark.parametrize('ram_gib,vram_gib,accepted', [(16, 21.4, True), (13, 21.4, False), (16, 20.9, False)])
def test_resource_gate_uses_host_minima_without_removing_allocator_cap(tmp_path, monkeypatch, ram_gib, vram_gib, accepted):
    calls = []
    cuda = types.SimpleNamespace(is_available=lambda: True,
        mem_get_info=lambda: (int(vram_gib * 1024**3), 24 * 1024**3),
        get_device_properties=lambda _: types.SimpleNamespace(total_memory=24 * 1024**3),
        set_per_process_memory_fraction=lambda value: calls.append(value))
    monkeypatch.setitem(sys.modules, 'torch', types.SimpleNamespace(cuda=cuda,
        backends=types.SimpleNamespace(cuda=types.SimpleNamespace(enable_math_sdp=lambda value: calls.append(value)))))
    monkeypatch.setitem(sys.modules, 'psutil', types.SimpleNamespace(
        virtual_memory=lambda: types.SimpleNamespace(available=int(ram_gib * 1024**3))))
    context = WorkerContext(tmp_path, mode='gpu', epoch='fixture')
    monkeypatch.setattr(context, 'require_gpu', lambda: None)
    if accepted:
        context.preflight_resources()
        assert calls == [20 / 24, False]
    else:
        with pytest.raises(ValueError, match='RAM|VRAM'):
            context.preflight_resources()
        assert calls == []


def test_admission_progress_does_not_require_prompt_but_other_threads_keep_hook(monkeypatch):
    import threading
    from video_ai.experiments.wan_wrapper_runtime_support import admission_progress_scope
    events = []
    def original(*args, **kwargs):
        if threading.current_thread() is threading.main_thread():
            raise AttributeError('no last_prompt_id before first video')
        events.append(args)
    utils = types.SimpleNamespace(PROGRESS_BAR_HOOK=original)
    utils.set_progress_bar_global_hook = lambda hook: setattr(utils, 'PROGRESS_BAR_HOOK', hook)
    monkeypatch.setitem(sys.modules, 'comfy', types.SimpleNamespace(utils=utils))
    monkeypatch.setitem(sys.modules, 'comfy.utils', utils)
    with admission_progress_scope():
        utils.PROGRESS_BAR_HOOK(1, 1095, None, node_id=None)
        thread = threading.Thread(target=lambda: utils.PROGRESS_BAR_HOOK(2, 1095, None))
        thread.start(); thread.join()
    assert events == [(2, 1095, None)]
    assert utils.PROGRESS_BAR_HOOK is original
    with pytest.raises(RuntimeError):
        with admission_progress_scope():
            raise RuntimeError('model load failure')
    assert utils.PROGRESS_BAR_HOOK is original


def test_actual_admission_wraps_loading_before_any_video_prompt(tmp_path, monkeypatch):
    from uuid import uuid4
    from video_ai.experiments import wan_wrapper_lora as lora, wan_wrapper_runtime_support as support
    from video_ai.experiments.wan_fast_profiles import write_once
    def needs_prompt(*args, **kwargs):
        raise AttributeError('last_prompt_id')
    utils = types.SimpleNamespace(PROGRESS_BAR_HOOK=needs_prompt)
    utils.set_progress_bar_global_hook = lambda hook: setattr(utils, 'PROGRESS_BAR_HOOK', hook)
    monkeypatch.setitem(sys.modules, 'comfy', types.SimpleNamespace(utils=utils))
    monkeypatch.setitem(sys.modules, 'comfy.utils', utils)
    monkeypatch.setattr(support, 'InputLeases', lambda models: types.SimpleNamespace(close=lambda: None,verify=lambda:None))
    def pair(*args):
        utils.PROGRESS_BAR_HOOK(1, 1095, None, node_id=None)
        return types.SimpleNamespace(receipt={'full_model_verified': True})
    monkeypatch.setattr(lora, 'admit_pair', pair)
    ctx = WorkerContext(tmp_path, mode='gpu', epoch='fixture')
    monkeypatch.setattr(ctx, 'require_gpu', lambda: None)
    monkeypatch.setattr(ctx, 'preflight_resources', lambda **kw: None)
    ctx.profiles = {'fast': types.SimpleNamespace(digest=lambda: 'a' * 64)}
    ctx.factory = types.SimpleNamespace()
    ctx.comparison_sha256='b'*64;ctx.text_cache={}
    ctx.text_receipt={'epoch':'fixture','comparison_sha256':'b'*64,'image_prepared':True}
    ctx.image_cache={};ctx.vae_cache=object()
    admission_id = str(uuid4())
    write_once(tmp_path/'admission/client-intent.json', dict(admission_id=admission_id, profile_sha256='a'*64, epoch='fixture'))
    assert ctx.admit(admission_id)['receipt']['full_model_verified']
    assert utils.PROGRESS_BAR_HOOK is needs_prompt
    # A rejected admission must keep its concrete cause for original-ID GET.
    import json
    ctx.root=tmp_path/'failure'
    (ctx.root/'admission').mkdir(parents=True)
    from uuid import uuid4
    admission_id=str(uuid4())
    from video_ai.experiments.wan_fast_profiles import write_once
    write_once(ctx.root/'admission/client-intent.json',dict(admission_id=admission_id,
        profile_sha256=ctx.profiles['fast'].digest(),epoch=ctx.epoch))
    def reject(*args):raise ValueError('actual tensor target mismatch')
    monkeypatch.setattr(lora,'admit_pair',reject)
    with pytest.raises(ValueError,match='target mismatch'):ctx.admit(admission_id)
    failed=json.loads((ctx.root/'admission/failed.json').read_text(encoding='utf-8'))
    assert failed['error_message']=='actual tensor target mismatch'


def test_controller_commit_floor_before_bounded_gpu_process(monkeypatch):
    module=controller_module()
    monkeypatch.setattr(module,'host_available_commit_bytes',lambda:26*1024**3-1,raising=False)
    with pytest.raises(ValueError,match='commit'):module.preflight_host_commit()
    monkeypatch.setattr(module,'host_available_commit_bytes',lambda:26*1024**3)
    proof=module.preflight_host_commit()
    assert proof==dict(available_commit_bytes=26*1024**3,min_available_commit_bytes=26*1024**3,process_private_commit_bytes=18*1024**3)
