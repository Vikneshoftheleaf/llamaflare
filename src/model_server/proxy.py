from __future__ import annotations

import hmac
import os

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


@app.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def authenticated_proxy(path: str, request: Request):
    expected_key = os.environ.get("MODEL_SERVER_API_KEY", "")
    authorization = request.headers.get("authorization", "")
    supplied_key = authorization[7:] if authorization.lower().startswith("bearer ") else ""
    if not expected_key or not hmac.compare_digest(supplied_key, expected_key):
        return JSONResponse(
            {"detail": "A valid bearer token is required."},
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )

    upstream = os.environ.get("MODEL_SERVER_UPSTREAM", "http://127.0.0.1:8080").rstrip("/")
    target_url = f"{upstream}/{path}"
    if request.url.query:
        target_url += f"?{request.url.query}"
    headers = {
        name: value
        for name, value in request.headers.items()
        if name.lower() not in HOP_BY_HOP_HEADERS | {"host", "authorization", "content-length"}
    }

    client = httpx.AsyncClient(timeout=None)
    try:
        upstream_request = client.build_request(
            request.method,
            target_url,
            headers=headers,
            content=await request.body(),
        )
        upstream_response = await client.send(upstream_request, stream=True)
    except httpx.HTTPError as exc:
        await client.aclose()
        return JSONResponse(
            {"detail": f"Unable to reach the local model server: {exc}"},
            status_code=502,
        )

    response_headers = {
        name: value
        for name, value in upstream_response.headers.items()
        if name.lower() not in HOP_BY_HOP_HEADERS | {"content-length", "content-encoding"}
    }

    async def stream_response():
        try:
            async for chunk in upstream_response.aiter_raw():
                yield chunk
        finally:
            await upstream_response.aclose()
            await client.aclose()

    return StreamingResponse(
        stream_response(),
        status_code=upstream_response.status_code,
        headers=response_headers,
    )


def main() -> None:
    api_key = os.environ.get("MODEL_SERVER_API_KEY", "")
    if not api_key:
        raise RuntimeError("MODEL_SERVER_API_KEY must be configured before starting the proxy.")
    port = int(os.environ.get("MODEL_SERVER_PROXY_PORT", "8081"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
