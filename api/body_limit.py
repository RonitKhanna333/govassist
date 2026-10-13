"""Reject oversized request bodies before a route reads them.

Every JSON route here takes a few hundred bytes; only /transcribe takes
audio. Without a cap, a multi-megabyte JSON body is parsed in full before
any field-level `max_length` gets a say. The declared Content-Length is
checked up front, and a body sent without one (chunked) is counted as it
streams and buffered only up to the limit, so neither path can exceed it.
"""

from __future__ import annotations

import json

JSON_BODY_LIMIT = 64 * 1024
AUDIO_BODY_LIMIT = 4 * 1024 * 1024  # under Vercel's 4.5 MB request ceiling


def limit_for(path: str) -> int:
    return AUDIO_BODY_LIMIT if path.rstrip("/") == "/transcribe" else JSON_BODY_LIMIT


class BodySizeLimitMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit = limit_for(scope.get("path", ""))
        for name, value in scope.get("headers", []):
            if name == b"content-length":
                try:
                    declared = int(value)
                except ValueError:
                    declared = limit + 1
                if declared > limit:
                    await _reject(send, limit)
                    return

        # Read the (bounded) body here and replay it. Raising from inside the
        # app's own receive() doesn't work: FastAPI turns any error while
        # reading a body into a generic 400.
        chunks: list[bytes] = []
        received = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            received += len(chunk)
            if received > limit:
                await _reject(send, limit)
                return
            chunks.append(chunk)
            if not message.get("more_body", False):
                break

        body = b"".join(chunks)
        replayed = False

        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


async def _reject(send, limit: int) -> None:
    body = json.dumps({
        "detail": f"Request body too large (limit {limit // 1024} KB).",
    }).encode()
    await send({"type": "http.response.start", "status": 413,
                "headers": [(b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})
