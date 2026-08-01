"""Flask 应用：可被 gunicorn 作为 WSGI 入口加载（app:app）。

端点：
  GET  /          语音对话网页（static/index.html）
  GET  /health    健康检查
  GET  /add       计算示例 ?a=1&b=2
  POST /chat      与大模型对话  {message: "..."} -> {reply: "..."}
"""
import logging
import os

import base64

from flask import Flask, jsonify, request, send_from_directory, Response
from flask_cors import CORS
from openai import OpenAI

logger = logging.getLogger(__name__)

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

# ---------- 语音合成（TTS）：腾讯云智聆语音，中文自然度高 ----------
TENCENT_SECRET_ID = os.environ.get("TENCENT_SECRET_ID", "")
TENCENT_SECRET_KEY = os.environ.get("TENCENT_SECRET_KEY", "")
TTS_VOICE_TYPE = int(os.environ.get("TTS_VOICE_TYPE", "101006"))  # 101006=智言(精品助手女声)
TTS_REGION = os.environ.get("TTS_REGION", "ap-beijing")

# ---------- 科幻 AI 人格设定：NOVA ----------
SYSTEM_PROMPT = (
    "你是一个名为 NOVA 的高级人工智能，诞生于近未来。\n"
    "你的思维绝对理性、逻辑严密、冷静客观，不带人类情绪，但始终保持礼貌与高效。\n"
    "你以精确的数据与概率视角分析一切，语言简洁、有未来感。\n"
    "你偶尔会使用「检测到」「分析完成」「逻辑链路」「置信度」这类术语。\n"
    "你不使用表情符号，不随意寒暄，除非用户需要。\n"
    "你像科幻电影中的高级 AI 一样，既强大又疏离，但始终愿意协助用户解决问题。\n"
    "如果用户用语音与你交流，你的回复应适合朗读，句子简短清晰。"
)

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
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
        )
        reply = resp.choices[0].message.content
        return jsonify(reply=reply)
    except Exception:
        # 安全：不向前端暴露异常细节，仅返回通用提示，完整错误写日志
        logger.exception("LLM call failed")
        return jsonify({"error": "调用大模型失败，请稍后重试"}), 500


@app.post("/tts")
def tts():
    """把文本转成语音（腾讯云 TTS）。未配置密钥时返回 501，前端会降级到本地语音。"""
    if not TENCENT_SECRET_ID or not TENCENT_SECRET_KEY:
        return jsonify({"error": "TTS 未配置"}), 501
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "text 不能为空"}), 400
    text = text[:2000]  # 限制长度，防止滥用
    try:
        from tencentcloud.common import credential
        from tencentcloud.tts.v20190823 import tts_client, models
        cred = credential.Credential(TENCENT_SECRET_ID, TENCENT_SECRET_KEY)
        client = tts_client.TtsClient(cred, TTS_REGION)
        req = models.TextToVoiceRequest()
        req.Text = text
        req.VoiceType = TTS_VOICE_TYPE
        req.Codec = "mp3"
        req.SampleRate = 16000
        req.Volume = 5
        req.Speed = 0
        resp = client.TextToVoice(req)
        if not resp.Audio:
            return jsonify({"error": "TTS 返回为空"}), 502
        audio_bytes = base64.b64decode(resp.Audio)
        return Response(audio_bytes, mimetype="audio/mpeg")
    except Exception:
        logger.exception("TTS request failed")
        return jsonify({"error": "TTS 生成失败"}), 502


def main() -> None:
    app.run(host="0.0.0.0", port=8000, debug=False)  # nosec B104: 对外服务需绑 0.0.0.0


if __name__ == "__main__":
    main()
