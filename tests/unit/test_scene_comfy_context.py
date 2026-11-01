"""Network send guards retain the caller's authenticated validation scope."""
from video_ai.adapters.scene_comfy import SceneComfyClient
from video_ai.runtime.scene_execution_records import _writer_admissions
from video_ai.runtime.verification import validation_session,validation_memo


def test_network_guards_keep_authenticated_caller_scope():
    class Transport:
        def request(self,method,route,*,body,timeout,ownership_check):
            ownership_check()
            return dict(status=200,headers={},body=b'{"queue_running":[],"queue_pending":[]}')
    admitted={'fixture':'already authenticated in caller'}
    token=_writer_admissions.set(admitted)
    try:
        with validation_session():
            expected=validation_memo('send-guard-scope')
            expected['binding']='caller-byte-proof'
            def guard():
                if _writer_admissions.get() is not admitted or validation_memo('send-guard-scope') is not expected:
                    raise RuntimeError('network guard lost authenticated caller scope')
            client=SceneComfyClient('http://127.0.0.1:8188',request_timeout=1,ownership_check=guard,http=Transport())
            result=client.queue(timeout=1)
            assert result['status']==200 and result['body']==b'{"queue_running":[],"queue_pending":[]}'
    finally:_writer_admissions.reset(token)
