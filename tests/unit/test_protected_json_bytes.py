import os
import pytest
from video_ai.runtime import verification, manifest, scene_revision_records
from video_ai.config import read_json

pytestmark=pytest.mark.skipif(os.name!='nt',reason='native mandatory sharing')

def test_json_and_revision_read_share_protected_bytes(tmp_path,monkeypatch):
    path=tmp_path/'leaf.json';path.write_text('{"v":1}',encoding='utf8')
    calls=[];original=verification._read_open_bytes
    def counted(*args):calls.append(1);return original(*args)
    monkeypatch.setattr(verification,'_read_open_bytes',counted)
    with verification.whole_input_protection(), verification.validation_session():
        assert read_json(path)=={'v':1}
        assert scene_revision_records.stable_bytes(path,root=tmp_path)==b'{"v":1}'
        assert manifest.hash_file(path).bytes==7
        assert read_json(path)=={'v':1}
        assert len(calls)==1
        with pytest.raises(OSError):path.write_bytes(b'changed')
    path.write_bytes(b'{"v":2}')
    with verification.whole_input_protection(),verification.validation_session():
        assert read_json(path)=={'v':2}
    assert len(calls)==2

def test_mutable_writer_bytes_are_not_reused(tmp_path):
    path=tmp_path/'leaf.json';path.write_bytes(b'{"v":1}')
    with verification.whole_input_protection(),verification.writable_validation_session(tmp_path):
        assert read_json(path)=={'v':1}
        path.write_bytes(b'{"v":2}')
        assert read_json(path)=={'v':2}

def test_writer_promotion_discards_previously_cached_bytes(tmp_path):
    path=tmp_path/'leaf.json';path.write_bytes(b'{"v":1}')
    with verification.whole_input_protection(), verification.validation_session():
        window=verification._whole_inputs.get()
        assert read_json(path)=={'v':1}
        assert path in window.byte_contents
        with verification.writable_validation_session(tmp_path):
            assert path not in window.byte_contents
            path.write_bytes(b'{"v":2}')
            assert read_json(path)=={'v':2}
    assert not window.byte_contents

def test_cached_bytes_are_observed_by_each_capture(tmp_path):
    from video_ai.runtime._continuity_byte_guard import capture_reads
    path=tmp_path/'leaf.json';path.write_bytes(b'{"v":1}')
    with verification.whole_input_protection(),verification.validation_session():
        read_json(path)
        for _ in range(2):
            with capture_reads() as capture:
                assert read_json(path)=={'v':1}
            guard=capture.finish()
            assert guard.file_count==1
            guard.verify()

def test_submission_and_script_reuse_existing_protected_bytes(tmp_path,monkeypatch):
    import hashlib
    from video_ai.runtime import image_selection_records as images, production_inputs
    raw=b'{"v":1}';sha=hashlib.sha256(raw).hexdigest()
    folder=tmp_path/'submissions';folder.mkdir();path=folder/(sha+'.json');path.write_bytes(raw)
    script=tmp_path/'script.txt';script.write_bytes(b'example text')
    calls=[];original=verification._read_open_bytes
    from pathlib import Path
    direct=[];original_direct=Path.read_bytes
    def direct_read(current):
        direct.append(current)
        return original_direct(current)
    monkeypatch.setattr(Path,'read_bytes',direct_read)
    def counted(file,path):calls.append(path);return original(file,path)
    monkeypatch.setattr(verification,'_read_open_bytes',counted)
    with verification.whole_input_protection(),verification.validation_session():
        manifest.hash_file(path)
        images._submission(tmp_path,sha);images._submission(tmp_path,sha)
        manifest.hash_file(script)
        production_inputs.read_script(script=script)
        production_inputs.read_script(script=script)
    assert calls.count(path)==1
    assert calls.count(script)==1
    assert path not in direct and script not in direct

def test_window_reuses_bytes_and_hashes_between_validation_sessions(tmp_path,monkeypatch):
    path=tmp_path/'leaf.json';path.write_bytes(b'{"v":1}')
    image=tmp_path/'image.original';image.write_bytes(b'image bytes')
    reads=[];hashes=[]
    original_read=verification._read_open_bytes;original_hash=manifest._hash_open_file
    def read(file,path):reads.append(path);return original_read(file,path)
    def hashed(file,path):hashes.append(path);return original_hash(file,path)
    monkeypatch.setattr(verification,'_read_open_bytes',read)
    monkeypatch.setattr(manifest,'_hash_open_file',hashed)
    with verification.whole_input_protection():
        for _ in range(3):
            assert read_json(path)=={'v':1}
            manifest.hash_file(path);manifest.hash_file(image)
    assert reads.count(path)==1
    assert hashes.count(image)==1

def test_large_json_uses_the_same_single_read_path(tmp_path,monkeypatch):
    path=tmp_path/'invalidation.json'
    path.write_bytes(b'{"value":"'+b'a'*(8*1024**2)+b'"}')
    calls=[];original=verification._read_open_bytes
    def read(file,current):calls.append(current);return original(file,current)
    monkeypatch.setattr(verification,'_read_open_bytes',read)
    with verification.whole_input_protection():
        manifest.hash_file(path)
        verification.read_bytes(path);verification.read_bytes(path)
    assert calls==[path]

def test_review_scope_reuses_append_only_inputs_and_allows_new_records(tmp_path,monkeypatch):
    from types import SimpleNamespace
    run=tmp_path/'run';folder=run/'production/scene-clips/s_clip';folder.mkdir(parents=True)
    (folder/'clip.json').write_bytes(b'{}')
    media=folder/'generated.mp4';media.write_bytes(b'existing immutable media')
    receipt=folder/'observation-accepted.json';receipt.write_bytes(b'{"v":1}')
    reference=run/'production/reference-images/wan-inputs.json'
    reference.parent.mkdir(parents=True);reference.write_bytes(b'{"ready":true}')
    frozen=SimpleNamespace(options={'script_path':str(run/'production/script.txt')},config=SimpleNamespace(production_strategy='paragraph_jimeng_v1',raw={}))
    monkeypatch.setattr(manifest,'validate_run_dir',lambda p:p)
    calls=[];original=manifest._hash_open_file
    def counted(file,path):calls.append(path);return original(file,path)
    monkeypatch.setattr(manifest,'_hash_open_file',counted)
    content_reads=[];original_read=verification._read_open_bytes
    def content_read(file,path):content_reads.append(path);return original_read(file,path)
    monkeypatch.setattr(verification,'_read_open_bytes',content_read)
    with verification.scene_input_protection(frozen,review_only=True):
        manifest.hash_file(media);manifest.hash_file(media)
        assert read_json(reference)=={'ready':True}
        assert read_json(reference)=={'ready':True}
        assert read_json(receipt)=={'v':1}
        assert read_json(receipt)=={'v':1}
        with pytest.raises(OSError):receipt.write_bytes(b'{"v":2}')
        observations=folder/'observations';observations.mkdir()
        appended=observations/'new.json';appended.write_bytes(b'{"v":3}')
        assert read_json(appended)=={'v':3}
        assert read_json(appended)=={'v':3}
        with pytest.raises(OSError):media.write_bytes(b'changed')
    assert calls.count(media)==1
    assert content_reads.count(reference)==1
    assert content_reads.count(receipt)==1
    assert content_reads.count(appended)==1

def test_standalone_input_read_gets_a_fresh_protected_window(tmp_path,monkeypatch):
    path=tmp_path/'input.json';path.write_bytes(b'{"v":1}')
    calls=[];original=verification._read_open_bytes
    def counted(file,current):calls.append(current);return original(file,current)
    monkeypatch.setattr(verification,'_read_open_bytes',counted)
    @verification.protected_input_read
    def load():
        manifest.hash_file(path)
        return read_json(path),read_json(path)
    assert load()==({'v':1},{'v':1})
    assert calls==[path]
    path.write_bytes(b'{"v":2}')
    assert load()==({'v':2},{'v':2})
    assert calls==[path,path]
