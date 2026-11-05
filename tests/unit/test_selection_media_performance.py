"""Actual tiny-media command counts; originals and provenance stay immutable."""
from unit.test_selection_sheet import sheet_context, batch_for


def test_previews_share_one_input_decode_and_promotion_proof(sheet_context, monkeypatch):
    from video_ai.media import selection_sheet as sheet
    run, kwargs = sheet_context
    commands = []
    original = sheet._Media.command
    def counted(self, args):
        commands.append(tuple(map(str, args)))
        return original(self, args)
    monkeypatch.setattr(sheet._Media, 'command', counted)
    media = sheet.prepare_email_media(batch_for(run), **kwargs)
    renders = [args for args in commands if 'mjpeg' in args and '-frames:v' in args]
    assert len(renders) == 2  # one four-output preview decode, one contact sheet
    assert len(media['images']) == 5
    # One source decode, four preview decodes, one sheet decode. A byte-identical
    # promotion changes only the verified path, not the decoded image fact.
    probes = [args for args in commands if '-show_streams' in args]
    assert len(probes) == 6


def test_multi_output_previews_match_existing_single_output_jpegs(sheet_context):
    from video_ai.media import selection_sheet as sheet
    run, kwargs = sheet_context
    batch = batch_for(run)
    source = batch['scenes'][0]['candidates'][0]
    store = sheet._Media(**kwargs)
    folder = run/'production/image-selection/image_batch_0002/mail/previews'
    old = []
    for width, height in sheet.PREVIEW_SIZES:
        target = folder/f'scene_0002--{source["candidate_id"]}--{width}x{height}.jpg'
        recipe = f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1'
        old.append(store.render(target, ('-i', source['path'], '-vf', recipe)))
    media = sheet.prepare_email_media(batch, **kwargs)
    assert [{k:r[k] for k in ('path', 'bytes', 'sha256', 'width', 'height')}
            for r in media['images'][1:]] == old
