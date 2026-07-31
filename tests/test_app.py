"""示例测试：覆盖示例应用的三个端点。"""

from app import app


def test_index_returns_welcome() -> None:
    """首页返回语音对话界面（HTML）。"""
    client = app.test_client()
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "AI 语音对话" in html or "chat" in html.lower()


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