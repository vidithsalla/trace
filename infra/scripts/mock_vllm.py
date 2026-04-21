import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path in {"/health", "/v1/models"}:
            payload = (
                {"status": "ok", "service": "mock-vllm"}
                if self.path == "/health"
                else {
                    "object": "list",
                    "data": [
                        {
                            "id": "trace-placeholder-model",
                            "object": "model",
                            "owned_by": "trace",
                        }
                    ],
                }
            )
            self._send(200, payload)
            return
        self._send(404, {"detail": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/v1/chat/completions":
            self._send(
                200,
                {
                    "id": "chatcmpl-trace-placeholder",
                    "object": "chat.completion",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": "Trace Phase 0 model placeholder is reachable.",
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                },
            )
            return
        self._send(404, {"detail": "not found"})


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 8001), Handler)
    server.serve_forever()
