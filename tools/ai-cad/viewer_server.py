"""Bounded socket concurrency; completed CAD requests still execute serially."""

from http.server import ThreadingHTTPServer
import threading


class ViewerServer(ThreadingHTTPServer):
    # Idle/preconnected browser sockets must not monopolize request parsing.
    # Bound threads and queued connections, and finish active writes on shutdown.
    daemon_threads = False
    block_on_close = True
    request_queue_size = 32
    max_connections = 16
    socket_timeout = 5

    def __init__(self, *args, **kwargs):
        self.slots = threading.BoundedSemaphore(self.max_connections)
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            # Do not block the accept loop behind clients that have not sent headers.
            try:
                request.settimeout(0.1)
                request.sendall(
                    b"HTTP/1.1 503 Service Unavailable\r\nConnection: close\r\nContent-Length: 0\r\nRetry-After: 1\r\n\r\n"
                )
            except OSError:
                pass
            finally:
                self.shutdown_request(request)
            return
        try:
            request.settimeout(self.socket_timeout)
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()
