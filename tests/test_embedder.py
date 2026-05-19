import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import EmbeddingConfig
from src.embedder import create_embedder, embedding_batch_size


def test_glm_default_batch_size_is_conservative():
    assert embedding_batch_size(EmbeddingConfig(provider="glm")) == 16
    assert embedding_batch_size(EmbeddingConfig(provider="local")) == 64
    assert embedding_batch_size(EmbeddingConfig(provider="glm", batch_size=8)) == 8


def test_glm_embedder_uses_openai_compatible_endpoint(monkeypatch):
    calls = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "data": [
                    {"index": 1, "embedding": [0.3, 0.4]},
                    {"index": 0, "embedding": [0.1, 0.2]},
                ]
            }

    def fake_post(url, headers, json, timeout):
        calls.append({
            "url": url,
            "headers": headers,
            "json": json,
            "timeout": timeout,
        })
        return Response()

    monkeypatch.setenv("ZHIPU_API_KEY", "test-key")
    monkeypatch.setattr("httpx.post", fake_post)

    embedder = create_embedder(EmbeddingConfig(
        provider="glm",
        dimensions=1024,
        timeout=12.5,
    ))
    result = embedder.embed(["hello", "world"])

    assert result == [[0.1, 0.2], [0.3, 0.4]]
    assert calls[0]["url"] == "https://open.bigmodel.cn/api/paas/v4/embeddings"
    assert calls[0]["headers"]["Authorization"] == "Bearer test-key"
    assert calls[0]["json"] == {
        "model": "embedding-3",
        "input": ["hello", "world"],
        "dimensions": 1024,
    }
    assert calls[0]["timeout"] == 12.5


def test_openai_compatible_requires_base_url():
    try:
        create_embedder(EmbeddingConfig(
            provider="openai_compatible",
            api_key="test-key",
            model="embedding-3",
        ))
    except ValueError as exc:
        assert "base_url" in str(exc)
    else:
        raise AssertionError("missing base_url should fail")


def test_embedding_http_400_includes_response_body(monkeypatch):
    import httpx

    class Response:
        status_code = 400
        text = '{"error":"input too long"}'

        def raise_for_status(self):
            request = httpx.Request("POST", "https://example.com/v1/embeddings")
            response = httpx.Response(
                400,
                request=request,
                text=self.text,
            )
            raise httpx.HTTPStatusError(
                "bad request",
                request=request,
                response=response,
            )

    monkeypatch.setattr("httpx.post", lambda *args, **kwargs: Response())

    embedder = create_embedder(EmbeddingConfig(
        provider="openai_compatible",
        api_key="test-key",
        base_url="https://example.com/v1",
        model="embedding-3",
        max_retries=1,
    ))

    try:
        embedder.embed(["x" * 10])
    except RuntimeError as exc:
        message = str(exc)
        assert "HTTP 400" in message
        assert "input too long" in message
        assert "longest_chars=10" in message
        assert "preview=" in message
    else:
        raise AssertionError("HTTP 400 should fail with diagnostic body")


def test_embedding_splits_batch_after_http_400(monkeypatch):
    import httpx

    calls = []

    class OKResponse:
        def __init__(self, count):
            self.count = count

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "data": [
                    {"index": i, "embedding": [float(i)]}
                    for i in range(self.count)
                ]
            }

    class BadResponse:
        status_code = 400
        text = '{"error":"bad batch"}'

        def raise_for_status(self):
            request = httpx.Request("POST", "https://example.com/v1/embeddings")
            response = httpx.Response(400, request=request, text=self.text)
            raise httpx.HTTPStatusError(
                "bad request",
                request=request,
                response=response,
            )

    def fake_post(url, headers, json, timeout):
        inputs = list(json["input"])
        calls.append(inputs)
        if len(inputs) > 1:
            return BadResponse()
        return OKResponse(len(inputs))

    monkeypatch.setattr("httpx.post", fake_post)

    embedder = create_embedder(EmbeddingConfig(
        provider="openai_compatible",
        api_key="test-key",
        base_url="https://example.com/v1",
        model="embedding-3",
        max_retries=1,
    ))

    assert embedder.embed(["a", "b", "c"]) == [[0.0], [0.0], [0.0]]
    assert calls == [["a", "b", "c"], ["a"], ["b", "c"], ["b"], ["c"]]


def test_embedding_sanitizes_control_characters(monkeypatch):
    seen = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": [{"index": 0, "embedding": [1.0]}]}

    def fake_post(url, headers, json, timeout):
        seen.append(json["input"][0])
        return Response()

    monkeypatch.setattr("httpx.post", fake_post)

    embedder = create_embedder(EmbeddingConfig(
        provider="openai_compatible",
        api_key="test-key",
        base_url="https://example.com/v1",
        model="embedding-3",
    ))

    assert embedder.embed(["a\x00\x01\n\nb"]) == [[1.0]]
    assert seen == ["a b"]


def test_embedding_splits_batch_after_protocol_error(monkeypatch):
    import httpx

    calls = []

    class Response:
        def __init__(self, count):
            self.count = count

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "data": [
                    {"index": i, "embedding": [float(i)]}
                    for i in range(self.count)
                ]
            }

    def fake_post(url, headers, json, timeout):
        calls.append(list(json["input"]))
        if len(json["input"]) > 1:
            raise httpx.RemoteProtocolError("incomplete chunked read")
        return Response(len(json["input"]))

    monkeypatch.setattr("httpx.post", fake_post)

    embedder = create_embedder(EmbeddingConfig(
        provider="openai_compatible",
        api_key="test-key",
        base_url="https://example.com/v1",
        model="embedding-3",
        max_retries=1,
    ))

    assert embedder.embed(["a", "b", "c"]) == [[0.0], [0.0], [0.0]]
    assert calls == [["a", "b", "c"], ["a"], ["b", "c"], ["b"], ["c"]]
