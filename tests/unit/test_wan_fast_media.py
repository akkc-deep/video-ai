import pytest

from video_ai.experiments.wan_fast_media import black_frame_summary


def test_near_black_requires_two_consecutive_whole_frames():
    black = bytes([1, 0, 1] * 4)
    white = bytes([255] * 12)
    result = black_frame_summary(black + white + black, width=2, height=2)
    assert result == {'frames': 3, 'suspect_black': False, 'longest_black_run': 1}
    assert black_frame_summary(white + black + black, width=2, height=2)['suspect_black']
    with pytest.raises(ValueError, match='truncated'):
        black_frame_summary(b'\0', width=2, height=2)


def test_dark_pixel_fraction_checks_all_rgb_channels():
    # Two frames with one bright pixel each: not 99.9% near-black.
    frame = bytes([0] * (3*999) + [0, 2, 0] * 2)
    assert not black_frame_summary(frame*2, width=1001, height=1)['suspect_black']
