"""Full inventories retain path guards without repeating sibling ancestor walks."""
from pathlib import Path
import os
import subprocess

import pytest

from video_ai.runtime._whole_scene_admission import EvidenceReader
from video_ai.runtime.production_state import ProductionRefused


def test_many_sibling_files_share_only_their_current_scan_ancestor_checks(runtime_run,monkeypatch):
    run,_,_=runtime_run;folder=run/'inventory';folder.mkdir()
    expected=[]
    for index in range(100):
        path=folder/f'{index:03d}.json';path.write_text('{}');expected.append(str(path))
    original=Path.lstat;root_checks=[]
    def counted(path,*args,**kwargs):
        if path==folder:root_checks.append(path)
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'lstat',counted)
    reader=EvidenceReader()
    assert reader.inventory(folder)==expected
    assert len(root_checks)<=4, f'sibling scan repeated {len(root_checks)} ancestor checks'
    root_checks.clear()
    reader.verify()
    assert root_checks, 'every subsequent verification must recheck the directory'


@pytest.mark.parametrize('mutation',['added','removed','renamed'])
def test_inventory_rescans_and_rejects_current_file_set_changes(runtime_run,mutation):
    run,_,_=runtime_run;folder=run/'inventory';folder.mkdir()
    path=folder/'first.json';path.write_text('{}')
    reader=EvidenceReader();reader.inventory(folder)
    if mutation=='added':(folder/'second.json').write_text('{}')
    elif mutation=='removed':path.unlink()
    else:path.rename(folder/'renamed.json')
    with pytest.raises(ProductionRefused,match='inventory changed'):reader.verify()


def test_nested_patterns_and_ignored_directories_keep_the_existing_file_set(runtime_run):
    run,_,_=runtime_run;folder=run/'inventory';folder.mkdir()
    for name in ('root.json','root.txt','nested/child.json','.git/ignored.json','nested/__pycache__/ignored.json'):
        path=folder/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('{}')
    assert EvidenceReader().inventory(folder,'*.json')==sorted([str(folder/'root.json'),str(folder/'nested/child.json')])


def test_inventory_rejects_a_redirected_parent_of_matching_files(runtime_run):
    run,_,_=runtime_run;folder=run/'inventory';folder.mkdir()
    outside=run/'outside';outside.mkdir();(outside/'child.json').write_text('{}')
    link=folder/'linked'
    if os.name=='nt':
        subprocess.run(['cmd','/c','mklink','/J',str(link),str(outside)],check=True,capture_output=True,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    else:link.symlink_to(outside,target_is_directory=True)
    # An explicit redirected inventory root must always be refused.
    with pytest.raises(ProductionRefused,match='redirected'):EvidenceReader().inventory(link)


def test_redirected_entry_is_rejected_before_enumerating_the_remaining_tree(runtime_run,monkeypatch):
    run,_,_=runtime_run;folder=run/'inventory';folder.mkdir()
    outside=run/'outside';outside.mkdir();(outside/'child.json').write_text('{}')
    link=folder/'linked'
    if os.name=='nt':
        subprocess.run(['cmd','/c','mklink','/J',str(link),str(outside)],check=True,capture_output=True,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    else:link.symlink_to(outside,target_is_directory=True)
    original=Path.rglob
    def entries():
        yield link/'child.json'
        pytest.fail('enumerated more entries after encountering redirected content')
    def guarded(path,*args,**kwargs):
        return entries() if path==folder else original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'rglob',guarded)
    with pytest.raises(ProductionRefused,match='redirected'):EvidenceReader().inventory(folder)


def test_file_disappearing_after_listing_keeps_the_original_inventory_semantics(runtime_run,monkeypatch):
    run,_,_=runtime_run;folder=run/'inventory';folder.mkdir()
    path=folder/'first.json';path.write_text('{}')
    original=Path.lstat;removed=[]
    def disappearing(value,*args,**kwargs):
        if value==path and not removed:
            path.unlink();removed.append(True)
            raise FileNotFoundError(str(path))
        return original(value,*args,**kwargs)
    monkeypatch.setattr(Path,'lstat',disappearing)
    assert EvidenceReader().inventory(folder)==[str(path)]
    assert removed and not path.exists()
