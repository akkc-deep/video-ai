"""Windows can retain a process object after exit while its Popen handle lives."""
import os
import subprocess
import sys

from video_ai.runtime.production_state import process_started_at


def test_retained_handle_to_exited_child_does_not_hold_run_ownership():
    child=subprocess.Popen([sys.executable,'-B','-c','pass'])
    assert child.wait(timeout=10)==0
    assert child._handle is not None
    assert process_started_at(child.pid) is None


def test_live_current_process_retains_exact_creation_identity():
    first=process_started_at(os.getpid())
    assert first is not None and first.isdigit()
    assert process_started_at(os.getpid())==first
