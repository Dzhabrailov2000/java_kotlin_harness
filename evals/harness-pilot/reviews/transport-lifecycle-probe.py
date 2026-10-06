#!/usr/bin/env python3
"""Local Recorder lifecycle probe; socket creation is forbidden in this process."""
import http.client
import http.server
import io
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import types

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import transport

OriginalServer = http.server.ThreadingHTTPServer


class FakeResponse:
    status = 200
    headers = {}

    def __init__(self, gate, entered):
        self.gate = gate
        self.entered = entered
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.closed = True

    def read1(self, _):
        self.entered.set()
        self.gate.wait()
        raise http.client.IncompleteRead(b'')


class FakeOpener:
    def __init__(self, phase):
        self.phase = phase
        self.gate = threading.Event()
        self.entered = threading.Event()
        self.response = FakeResponse(self.gate, self.entered)

    def open(self, request):
        if self.phase == 'open':
            self.entered.set()
            self.gate.wait()
            raise OSError('local fake header wait released')
        return self.response


class NoSocketServer(OriginalServer):
    def __init__(self, address, handler):
        self.Handler = handler
        self.stop_loop = threading.Event()
        self.loop_started = threading.Event()
        self.errors = []
        self.handler = None
        self.closed = False
        self.socket = types.SimpleNamespace(close=lambda: setattr(self, 'closed', True))

    def serve_forever(self):
        self.loop_started.set()
        self.stop_loop.wait()

    def shutdown(self):
        self.stop_loop.set()

    def finish_request(self, request, address):
        self.handler = threading.current_thread()
        handler = self.Handler.__new__(self.Handler)
        handler.rfile = io.BytesIO(b'{}')
        handler.wfile = io.BytesIO()
        handler.headers = {'Content-Length': '2'}
        handler.command = 'POST'
        handler.path = '/v1/messages'
        handler.send_response = lambda *_: None
        handler.send_header = lambda *_: None
        handler.end_headers = lambda: None
        handler.send_error = lambda *_: None
        handler.forward()

    def shutdown_request(self, _):
        pass

    def handle_error(self, *_):
        self.errors.append(type(sys.exc_info()[1]).__name__)


def forbid_network(*_, **__):
    raise AssertionError('Socket/network access forbidden in this local probe')


def main():
    original_socket = socket.socket
    original_connect = socket.create_connection
    socket.socket = forbid_network
    socket.create_connection = forbid_network
    transport.http.server.ThreadingHTTPServer = NoSocketServer
    print('Python:', sys.version.split()[0])
    print('Socket creation and socket.create_connection forbidden; no HTTP listener or API call.')
    try:
        for phase in ['open', 'read1']:
            with tempfile.TemporaryDirectory(prefix='pilot-lifecycle-review-', dir='/private/tmp') as folder:
                recorder = transport.Recorder(Path(folder) / 'http', 'https://api.anthropic.com')
                fake = FakeOpener(phase)
                recorder.opener = fake
                try:
                    recorder.__enter__()
                    assert recorder.server.loop_started.wait(2)
                    recorder.server.process_request(object(), ('in-memory', 0))
                    assert fake.entered.wait(2)
                    recorder.__exit__(None, None, None)
                    observation = {
                        'phase': phase,
                        'recorder_exit_returned': True,
                        'listening_socket_stub_closed': recorder.server.closed,
                        'serve_thread_alive': recorder.thread.is_alive(),
                        'handler_alive_after_exit': recorder.server.handler.is_alive(),
                        'handler_is_daemon': recorder.server.handler.daemon,
                        'response_acquired': phase == 'read1',
                        'response_closed_after_exit': fake.response.closed if phase == 'read1' else None,
                        'errors_before_release': list(recorder.server.errors),
                        'request_error_file_before_release': (Path(folder) / 'http/0000-error.json').exists(),
                    }
                    fake.gate.set()
                    recorder.server.handler.join(2)
                    assert not recorder.server.handler.is_alive()
                    observation.update(
                        errors_after_release=recorder.server.errors,
                        response_closed_after_release=fake.response.closed if phase == 'read1' else None,
                        request_error_file_after_release=(Path(folder) / 'http/0000-error.json').exists(),
                        handler_finished=True,
                    )
                    print(json.dumps(observation))
                finally:
                    fake.gate.set()
                    recorder.server.stop_loop.set()
                    if recorder.server.handler:
                        recorder.server.handler.join(2)
    finally:
        transport.http.server.ThreadingHTTPServer = OriginalServer
        socket.socket = original_socket
        socket.create_connection = original_connect


if __name__ == '__main__':
    main()
