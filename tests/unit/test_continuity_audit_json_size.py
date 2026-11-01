"""The JSON cap constrains data bytes rather than optional pretty whitespace."""
import json
from time import monotonic

import pytest

from video_ai.media._continuity_audit import AuditWindow


@pytest.fixture
def output_window(monkeypatch):
    window=object.__new__(AuditWindow)
    window.deadline=monotonic()+300
    saved=[]
    def save(name,data):
        saved.append((name,data))
        return {'saved':name}
    monkeypatch.setattr(window,'save_bytes',save)
    return window,saved


def test_large_vector_metrics_fit_existing_json_cap_without_losing_values(output_window):
    from video_ai.media._continuity_storage import GeometryDecoder
    window,saved=output_window
    window.packed_geometry=True
    value={'schema_version':1,'algorithm':'continuity_cv_v1','comparisons':[
        {'regions':[{'geometry':{'vectors':[],'sampled_pairs':[[[1,2],[3,4]]]*400000}}]}]}
    assert len(json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2).encode('utf-8'))>16777216
    assert window.save('metrics.json',value)=={'saved':'metrics.json'}
    assert len(saved)==1 and len(saved[0][1])<=16777216
    assert GeometryDecoder().decode(json.loads(saved[0][1]))==value


def test_small_audit_json_keeps_existing_bytes(output_window):
    window,saved=output_window
    value={'identity':'白鹭','vectors':[[0.1,0.2,0.3]]}
    window.save('metrics.json',value)
    assert saved[0][1]==json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2).encode('utf-8')


def test_large_measurement_mode_does_not_encode_next_calibration_control(output_window):
    window,saved=output_window;window.packed_geometry=True
    control={'schema_version':1,'case_id':'next_case','comparisons':[{'left':'a','right':'b'}]}
    window.save('controls/next_case.json',control)
    assert saved[0][1]==json.dumps(control,ensure_ascii=False,allow_nan=False,indent=2).encode('utf-8')


@pytest.mark.parametrize('value',[{'text':'x'*16777216},{'number':float('nan')}])
def test_json_still_rejects_oversized_compact_data_and_nonfinite_values_before_write(output_window,value):
    window,saved=output_window
    with pytest.raises(ValueError):window.save('metrics.json',value)
    assert not saved
