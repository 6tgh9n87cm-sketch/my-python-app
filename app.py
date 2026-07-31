"""Flask 应用：可被 gunicorn 作为 WSGI 入口加载（app:app）。

端点：
  GET  /          语音对话网页（static/index.html）
  GET  /health    健康检查
  GET  /add       计算示例 ?a=1&b=2
  POST /chat      与大模型对话  {message: "..."} -> {reply: "..."}
"""
import os

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from openai import OpenAI

app = Flask(__name__)
CORS(app)  # 允许浏览器跨域调用（本地打开网页也能访问云端接口）


# ---------- 读取 .env（密钥不进仓库，仅在服务器本地存在）----------
def _load_env(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())


_load_env()

LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com")
LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek-chat")

client = (
    OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
    if LLM_API_KEY
    else None
)


@app.get("/")
def index():
    return send_from_directory("static", "index.html")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/add")
def add() -> dict:
    try:
        a = int(request.args.get("a", 0))
        b = int(request.args.get("b", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "a and b must be integers"}), 400
    return {"result": a + b}


@app.post("/chat")
def chat():
    if client is None:
        return jsonify({"error": "服务器未配置 LLM_API_KEY，请在服务器 .env 中设置"}), 500

    data = request.get_json(silent=True) or {}
    user_msg = (data.get("message") or "").strip()
    if not user_msg:
        return jsonify({"error": "message 不能为空"}), 400

    try:
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "你是一个友好、耐心、乐于助人的中文语音助手，回答简洁自然。",
                },
                {"role": "user", "content": user_msg},
            ],
        )
        reply = resp.choices[0].message.content
        return jsonify(reply=reply)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": f"调用大模型失败：{exc}"}), 500


def main() -> None:
    app.run(host="0.0.0.0", port=8000, debug=False)


if __name__ == "__main__":
    main()
