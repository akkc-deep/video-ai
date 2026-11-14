from types import SimpleNamespace

import pytest

from video_ai.runtime.reference_settings import _options


def test_empty_frozen_capability_table_can_be_filled_by_first_supplement():
    frozen=SimpleNamespace(config=SimpleNamespace(raw=dict(reference_generation=None,
        reference_capabilities={},reference_storage=None)))
    supplement=dict(reference_generation=None,reference_capabilities={'jimeng_t2i_v40':'E:/verified-capability.json'},
                    reference_storage={'bucket':'existing-bucket'})
    assert _options(frozen,supplement)==supplement
    assert frozen.config.raw['reference_capabilities']=={}


def test_nonempty_frozen_capability_table_cannot_be_replaced():
    frozen=SimpleNamespace(config=SimpleNamespace(raw=dict(reference_generation=None,
        reference_capabilities={'jimeng_t2i_v40':'E:/original.json'},reference_storage=None)))
    with pytest.raises(ValueError,match='cannot replace'):
        _options(frozen,dict(reference_generation=None,reference_capabilities={'jimeng_t2i_v40':'E:/different.json'},reference_storage=None))


@pytest.mark.parametrize('configured',[None,{}])
def test_revision_keeps_bound_reference_settings_when_capability_table_is_empty(monkeypatch,configured):
    from video_ai.runtime._scene_revision_reference import target_reference_digest,marker_digest
    from video_ai.runtime import reference_settings
    from video_ai.jimeng_config import parse_image_generation
    from video_ai.runtime.manifest import thaw
    from unit.test_jimeng_config import image_settings
    import hashlib
    model=parse_image_generation(image_settings(),'test')
    profile=b'original verified profile'
    values=dict(reference_generation=None,
        reference_capabilities={model.req_key:'E:/not-present/bound-profile.json'},
        reference_storage=dict(bucket='original'))
    context=dict(values=values,raws={model.req_key:profile})
    frozen=SimpleNamespace(config=SimpleNamespace(raw=dict(reference_generation=None,
        reference_capabilities=configured,reference_storage=None),image_generation=model),options={})
    def choose(target,resolved,raws):
        assert resolved==values
        assert raws==context['raws']
        return model,dict(profile='verified'),dict(bucket='original')
    monkeypatch.setattr(reference_settings,'_choose',choose)
    expected=marker_digest(dict(model_settings=thaw(model),capability=dict(profile='verified'),
        capability_sha256=hashlib.sha256(profile).hexdigest(),storage=dict(bucket='original')))
    assert target_reference_digest(frozen,context)==expected
    assert frozen.config.raw['reference_capabilities']==configured
