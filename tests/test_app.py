"""示例测试：覆盖示例应用的三个端点。"""

from app import app


def test_index_returns_welcome() -> None:
    """首页返回 NOVA 科幻对话界面（HTML）。"""
    client = app.test_client()
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "NOVA" in html and "chat" in html.lower()


def test_health_check() -> None:
    """/health 始终返回 ok。"""
    client = app.test_client()
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_add_endpoint_valid_input() -> None:
    """/add 接受合法整数。"""
    client = app.test_client()
    resp = client.get("/add?a=2&b=3")
    assert resp.status_code == 200
    assert resp.get_json() == {"result": 5}


def test_add_endpoint_invalid_input() -> None:
    """/add 非法输入返回 400。"""
    client = app.test_client()
    resp = client.get("/add?a=foo&b=bar")
    assert resp.status_code == 400


# ---------- 流式对话 /chat/stream 测试 ----------


class _FakeDelta:
    """模拟 OpenAI SDK 流式 chunk 里的 delta。"""

    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.delta = _FakeDelta(content)


class _FakeChunk:
    """模拟 stream=True 返回的单个 chunk。"""

    def __init__(self, content: str) -> None:
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, chunks) -> None:
        self._chunks = chunks

    def create(self, **kwargs):
        assert kwargs.get("stream") is True, "/chat/stream 必须开启 stream=True"
        return iter(self._chunks)


class _FakeChat:
    def __init__(self, chunks) -> None:
        self.completions = _FakeCompletions(chunks)


class _FakeClient:
    """模拟 OpenAI 客户端，返回预设的流式片段。"""

    def __init__(self, chunks) -> None:
        self.chat = _FakeChat(chunks)


def test_chat_stream_returns_sse_chunks(monkeypatch) -> None:
    """/chat/stream 以 SSE 逐块返回 delta，结尾发 [DONE]，mimetype 为 text/event-stream。"""
    chunks = [_FakeChunk("你"), _FakeChunk("好"), _FakeChunk("，NOVA")]
    monkeypatch.setattr("app.client", _FakeClient(chunks))

    resp = app.test_client().post("/chat/stream", json={"message": "测试"})
    assert resp.status_code == 200
    assert resp.mimetype == "text/event-stream"
    body = resp.data.decode("utf-8")
    assert 'data: {"delta": "你"}' in body
    assert 'data: {"delta": "好"}' in body
    assert 'data: {"delta": "，NOVA"}' in body
    assert "data: [DONE]" in body


def test_chat_stream_empty_message_returns_400() -> None:
    """/chat/stream 空消息返回 400。"""
    resp = app.test_client().post("/chat/stream", json={"message": "   "})
    assert resp.status_code == 400


def test_chat_stream_no_key_returns_500(monkeypatch) -> None:
    """/chat/stream 未配置 LLM_API_KEY 时返回 500。"""
    monkeypatch.setattr("app.client", None)
    resp = app.test_client().post("/chat/stream", json={"message": "hi"})
    assert resp.status_code == 500