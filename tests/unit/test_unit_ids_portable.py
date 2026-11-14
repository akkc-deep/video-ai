import pytest

from video_ai.runtime.manifest import validate_unit


def test_unit_ids_do_not_depend_on_legacy_runs_directory():
    for kind, uid in [('shot','shot_0001'),('image','shot_0001'),('frame','shot_0001:frame_000001')]:
        validate_unit(kind, uid)


@pytest.mark.parametrize('uid',['shot_0000','shot_1','../shot_0001','shot_１２３４'])
def test_invalid_shot_ids_still_fail(uid):
    with pytest.raises(ValueError):
        validate_unit('shot', uid)
