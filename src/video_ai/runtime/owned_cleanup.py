"""Owned cleanup errors remain secondary to an active execution failure."""
import sys


def best_effort(action):
    """Diagnostics during failure handling cannot replace the original error."""
    try:return action()
    except BaseException:return None


def cleanup_preserving_exception(action, *, logger, stage):
    original=sys.exception()
    try:return action()
    except BaseException as exc:
        best_effort(lambda:logger.exception(stage,None,exc))
        if original is None:raise


def stop_owned_preserving_exception(manager,handle,logger,stage, *, require_stopped=False):
    if handle is None or not handle.owned:return
    def stop():
        manager.stop(handle)
        if require_stopped and (handle.process is None or handle.process.poll() is None):
            raise OSError('owned service shutdown unconfirmed; no successful draft')
    return cleanup_preserving_exception(stop,logger=logger,stage=stage)
