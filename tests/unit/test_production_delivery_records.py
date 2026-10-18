from copy import deepcopy
import pytest
from delivery_helpers import delivery_case


@pytest.mark.parametrize('change',['unknown','bool','run','order','temp','source','completed'])
def test_transaction_rejects_schema_order_and_source_drift(runtime_run,change):
    from video_ai.runtime.production_delivery import OutputLock, new_transaction
    from video_ai.runtime.production_delivery_records import validate_delivery_transaction
    run,frozen,_,_=delivery_case(runtime_run)
    with OutputLock(run,frozen.options['output_paths']['movie']) as lock:
        data=new_transaction(frozen,run,lock)
        validate_delivery_transaction(data,run,frozen=frozen)
        bad=deepcopy(data)
        if change=='unknown':bad['unknown']=1
        elif change=='bool':bad['schema_version']=True
        elif change=='run':bad['run_id']='other'
        elif change=='order':bad['operations']['subtitle']['status']='published'
        elif change=='temp':bad['operations']['movie']['temp_path']=bad['output_paths']['movie']
        elif change=='source':bad['source_records']['candidate']['bytes']+=1
        else:bad['status']='completed'
        with pytest.raises(ValueError):validate_delivery_transaction(bad,run,frozen=frozen)


@pytest.mark.parametrize('suffix',['foreign.mp4','foreign.srt','foreign.delivery.json'])
def test_frozen_targets_cannot_change_role(runtime_run,suffix):
    from video_ai.runtime.production_delivery_records import validate_targets
    run,frozen,_,_=delivery_case(runtime_run)
    targets=dict(frozen.options['output_paths']);targets['movie']=str(__import__('pathlib').Path(targets['movie']).with_name(suffix))
    with pytest.raises(ValueError):validate_targets(targets,run,frozen=frozen)


@pytest.mark.parametrize('change',['unknown','bool','frames_bool','duration_nan','human','semantics','sync','report','movie','check'])
def test_receipt_rejects_false_acceptance_and_nested_drift(runtime_run,change):
    from video_ai.runtime.production_delivery import OutputLock,publish_delivery
    from video_ai.runtime.production_delivery_records import validate_delivery_receipt
    run,frozen,_,_=delivery_case(runtime_run)
    with OutputLock(run,frozen.options['output_paths']['movie']) as lock:receipt=publish_delivery(frozen,run,lock)
    validate_delivery_receipt(receipt,run,frozen=frozen)
    if change=='unknown':receipt['human_full_film']='passed'
    elif change=='bool':receipt['schema_version']=True
    elif change=='frames_bool':receipt['media']['frames']=True
    elif change=='duration_nan':receipt['media']['duration_seconds']=float('nan')
    elif change=='human':receipt['human_review']='passed'
    elif change=='semantics':receipt['actual_video_semantics']='passed'
    elif change=='sync':receipt['actual_action_sync']='passed'
    elif change=='report':receipt['production_report']=str(run/'elsewhere.json')
    elif change=='movie':receipt['movie']['unknown']=1
    else:receipt['technical_checks']['final_media']='unverified'
    with pytest.raises(ValueError):validate_delivery_receipt(receipt,run,frozen=frozen)


@pytest.mark.parametrize('raw',[b'{"schema_version":1,"schema_version":1}',b'{"x":NaN}',b'{"x":Infinity}'])
def test_delivery_json_rejects_duplicate_and_nonfinite_keys(runtime_run,raw):
    from video_ai.config import read_json
    run,_,_=runtime_run;path=run/'invalid.json';path.write_bytes(raw)
    with pytest.raises(ValueError):read_json(path)


def test_output_reparse_is_refused_even_when_redirected_within_output_root(runtime_run):
    import os,subprocess
    from pathlib import Path
    from video_ai.runtime.paths import OUTPUT_ROOT
    from video_ai.runtime.production_delivery_records import output_path
    run,_,_=runtime_run
    directory=OUTPUT_ROOT/('delivery-junction-'+run.name);directory.mkdir()
    target=directory/'target';target.mkdir()
    junction=directory/'alias'
    result=subprocess.run(['powershell.exe','-NoProfile','-Command',
        '$ErrorActionPreference="Stop"; New-Item -ItemType Junction -Path $env:DELIVERY_JUNCTION -Target $env:DELIVERY_TARGET | Out-Null'],
        env={**os.environ,'DELIVERY_JUNCTION':str(junction),'DELIVERY_TARGET':str(target)},capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    try:
        with pytest.raises(ValueError):output_path(junction/'film.mp4')
    finally:junction.rmdir()
