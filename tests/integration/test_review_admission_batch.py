"""Real receipt admission for tiny testsrc fixtures; no model service or network."""
import hashlib
import json
from pathlib import Path

from scene_clip_helpers import OfflineWan, generate
from scene_pipeline_helpers import write_clip_observation
from integration.test_scene_revision_flow import revision_source
from video_ai.runtime import production_scene_clips as clips
from video_ai.planning.production_scenes import canonical_digest


def test_offline_batch_receipts_keep_original_bindings_and_one_scan(revision_source,monkeypatch):
    setup=revision_source
    backend=OfflineWan(setup)  # Caller-created tiny testsrc; never invokes a model.
    pending=generate(setup,backend)
    assert pending.status=='awaiting_continuity_review',pending.error
    observations=[write_clip_observation(setup,template) for template in pending.observation_templates]
    assert len(observations)>1
    prior_posts=len(backend.posts);prior_ensures=backend.ensures
    scans=[];original=clips.collect_progress
    def collect(*a,**kw): scans.append(1);return original(*a,**kw)
    monkeypatch.setattr(clips,'collect_progress',collect)
    result=clips.consume_scene_clip_observations(setup['frozen'],setup['units'],setup['timeline'],observations,
        paths=setup['paths'],logger=setup['logger'])
    # Accepting this parent exposes a pending child: retain the public batch's
    # early stop on the resulting blocked global state.
    assert result.status=='blocked',result.error
    assert len(scans)==1
    assert len(backend.posts)==prior_posts and backend.ensures==prior_ensures
    for path in observations[:1]:
        raw=path.read_bytes();value=json.loads(raw)
        folder=setup['run']/'production/scene-clips'/value['clip_id']
        receipt=json.loads((folder/'observation-accepted.json').read_bytes())
        assert receipt['observation']['sha256']==hashlib.sha256(raw).hexdigest()
        assert Path(receipt['observation']['path']).read_bytes()==raw
        assert receipt['clip_sha256']==canonical_digest(json.loads((folder/'clip.json').read_bytes()))
        assert receipt['request_sha256']==canonical_digest(json.loads((folder/'request.json').read_bytes()))
    for path in observations[1:]:
        value=json.loads(path.read_bytes())
        assert not (setup['run']/'production/scene-clips'/value['clip_id']/'observation-accepted.json').exists()
