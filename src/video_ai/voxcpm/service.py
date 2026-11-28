"""Serial execution with honest cooperative cancellation of synchronous inference."""
import threading

from .contracts import ApiError, freeze_request


class JobService:
    def __init__(self, store, binding, backend_factory, *, session_id=''):
        self.store, self.binding, self.backend_factory = store, dict(binding), backend_factory
        self.session_id = session_id
        self.state, self.error = 'loading', None
        self._stop = threading.Event()
        self._drain = threading.Event()
        self._wake = threading.Event()
        self._gate = threading.Lock()
        self._thread = threading.Thread(target=self._run, name='voxcpm-inference')

    def start(self):
        self._thread.start()

    def health(self):
        return dict(service='video-ai-voxcpm2', status=self.state, session_id=self.session_id,
                    model_revision=self.binding['model_revision'], error=self.error,
                    cancellation='cooperative_after_current_inference')

    def submit(self, body):
        request = freeze_request(body, self.binding)
        with self._gate:
            if self.state in ('failed', 'stopping'):
                raise ApiError(503, 'service unavailable')
            result = self.store.submit(request)
            self._wake.set()
            return result

    def cancel(self, request_id):
        return self.store.cancel(request_id)

    def close(self, *, finish_pending=False):
        with self._gate:
            self.state = 'stopping'
            if finish_pending:
                self._drain.set()
            else:
                self._stop.set()
                self.store.stop_pending()
            self._wake.set()
        if self._thread.ident is not None:
            self._thread.join()

    def _run(self):
        try:
            self._execute()
        except Exception as error:
            with self._gate:
                self.error = 'worker_failed: ' + str(error)
                self.state = 'failed'
                try:
                    self.store.stop_pending(self.error)
                except Exception:
                    pass  # Storage may itself be unavailable; health still rejects new work.

    def _execute(self):
        try:
            backend = self.backend_factory()
        except Exception as error:
            with self._gate:
                self.error = str(error)
                self.state = 'failed'
                self.store.stop_pending('model_load_failed: ' + str(error))
            return
        with self._gate:
            if not self._stop.is_set() and not self._drain.is_set():
                self.state = 'ready'
        while not self._stop.is_set():
            task = self.store.claim(self.binding)
            if task is None:
                if self._drain.is_set():
                    self._stop.set()
                    break
                self._wake.wait(.2)
                self._wake.clear()
                continue
            request_id = task['request_id']
            temporary = self.store.temporary(request_id)
            try:
                temporary.parent.mkdir(parents=True, exist_ok=True)
                metrics = backend.generate(task['request'], temporary)
                self.store.finish(request_id, temporary, metrics)
            except Exception as error:
                self.store.fail(request_id, error)
