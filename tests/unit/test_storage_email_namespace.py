"""Short internal revision numbers must not collide in external mail identities."""
from copy import deepcopy
from pathlib import Path

from unit.test_selection_email import email_batch, build


def test_two_videos_with_revision_01_have_distinct_message_ids(email_batch,tmp_path):
    batch,media = email_batch
    batch['run_id'] = '01'
    first = build(batch,media)[0]['message_id']
    other_batch,other_media = deepcopy(batch),deepcopy(media)
    for scene,image in zip(other_batch['scenes'],other_media['images']):
        source = Path(scene['candidates'][0]['path'])
        target = tmp_path/('other-video-'+source.name)
        target.write_bytes(source.read_bytes())
        scene['candidates'][0]['path'] = image['path'] = str(target)
    second = build(other_batch,other_media)[0]['message_id']
    assert first != second
    assert first == build(batch,media)[0]['message_id']
