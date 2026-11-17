from types import SimpleNamespace

import pytest

from video_ai.experiments.wan_fast_nodes import admit_pair, assert_sigmas, finite_images


class Model:
    def __init__(self, reject=False):
        self.reject = reject
        self.patched = False

    def clone(self):
        return Model(self.reject)

    def model_state_dict(self):
        return {'weight': SimpleNamespace(shape=(128, 256))}

    def add_patches(self, patches, strength):
        self.patched = True
        return [] if self.reject else list(patches)


def loaded(role, model):
    tensors = {'up': SimpleNamespace(shape=(128, 64)), 'down': SimpleNamespace(shape=(64, 256))}
    adapter = SimpleNamespace(name='lora', weights=(tensors['up'], tensors['down'], None, None, None, None),
                              loaded_keys=set(tensors))
    return tensors, {'weight': adapter}


def test_pair_returns_only_two_fully_admitted_clones():
    high, low = Model(), Model()
    result, counts = admit_pair(high, low, loaded)
    assert counts == {'high': 1, 'low': 1}
    assert all(m.patched for m in result)
    assert not high.patched and not low.patched


@pytest.mark.parametrize('failure', ['empty', 'unloaded', 'shape', 'rank', 'kind', 'partial', 'low_failure'])
def test_incompatible_pair_rejected_atomically(failure):
    high, low = Model(), Model(reject=failure == 'partial')
    def load(role, model):
        tensors, patches = loaded(role, model)
        patch = patches['weight']
        if failure == 'empty':
            return tensors, {}
        if failure == 'unloaded':
            tensors['ignored'] = object()
        if failure == 'shape':
            patch.weights[0].shape = (129, 64)
        if failure == 'rank':
            patch.weights[0].shape = (128, 63)
        if failure == 'kind':
            patch.name = 'loha'
        if failure == 'low_failure' and role == 'low':
            raise ValueError('incompatible_lora')
        return tensors, patches
    with pytest.raises(ValueError, match='incompatible_lora'):
        admit_pair(high, low, load)
    assert not high.patched and not low.patched


def test_sigma_mismatch_and_nan_rejected():
    assert_sigmas([1, .9375001, .8333333, .625, 0])
    for values in ([1, .9, .8, .6, 0], [1, float('nan'), .8333333, .625, 0], [1, 0]):
        with pytest.raises(ValueError, match='sigma'):
            assert_sigmas(values)

    class Tensor:
        def __init__(self, good): self.good = good
        def isfinite(self): return self
        def all(self): return self.good
    assert finite_images(Tensor(True)) is not None
    with pytest.raises(ValueError, match='nonfinite'):
        finite_images(Tensor(False))


def test_native_model_search_cannot_shadow_profiled_base(tmp_path):
    from video_ai.experiments.wan_fast_nodes import check_model_path
    from video_ai.experiments.wan_fast_profiles import artifact
    model = tmp_path/'models/expert.bin'; model.parent.mkdir(); model.write_bytes(b'original')
    shadow = tmp_path/'unet/expert.bin'; shadow.parent.mkdir(); shadow.write_bytes(b'foreign')
    folder = SimpleNamespace(get_full_path_or_raise=lambda category,name: str(model))
    check_model_path(folder, 'diffusion_models', 'expert.bin', [artifact(model)])
    folder.get_full_path_or_raise = lambda category,name: str(shadow)
    with pytest.raises(ValueError, match='model path'):
        check_model_path(folder, 'diffusion_models', 'expert.bin', [artifact(model)])
