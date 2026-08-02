"""Flask 应用：可被 gunicorn 作为 WSGI 入口加载（app:app）。

端点：
  GET  /             语音对话网页（static/index.html）
  GET  /health       健康检查
  GET  /add          计算示例 ?a=1&b=2
  POST /chat         与大模型对话（非流式）  {message: "..."} -> {reply: "..."}
  POST /chat/stream  与大模型流式对话（SSE） {message: "..."} -> data: {delta:"..."} / [DONE]
"""
import base64
import json
import logging
import os

from flask import Flask, Response, jsonify, request, send_from_directory
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

# ---------- 语音识别（ASR）：腾讯云一句话识别，16k 中文 ----------
ASR_REGION = os.environ.get("ASR_REGION", "ap-guangzhou")

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


@app.post("/chat/stream")
def chat_stream():
    """流式对话：SSE 逐块返回 NOVA 的回复（DeepSeek stream=True）。

    前端用 fetch + ReadableStream 读取，逐字渲染 + 闪烁光标。
    线上数据格式（SSE）：
        data: {"delta": "...片段..."}\\n\\n   （正常文本块，可能多次）
        data: {"error": "..."}\\n\\n           （出错时）
        data: [DONE]\\n\\n                     （流结束标志）
    注意：不使用 EventSource，因其仅支持 GET；这里保留 POST 请求体，
    用 fetch 流式读取，视觉上与 EventSource 逐字效果一致。
    """
    # 先校验输入，再查配置：无 key 时空消息也应是 400 而非 500（更符合预期）
    data = request.get_json(silent=True) or {}
    user_msg = (data.get("message") or "").strip()
    if not user_msg:
        return jsonify({"error": "message 不能为空"}), 400

    if client is None:
        return jsonify({"error": "服务器未配置 LLM_API_KEY，请在服务器 .env 中设置"}), 500

    def generate():
        try:
            stream = client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                stream=True,
            )
            for chunk in stream:
                # 某些 chunk 可能没有 choices（如首块角色声明），需跳过
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta.content
                if delta:
                    yield f"data: {json.dumps({'delta': delta}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception:
            # 安全：流中出错也只发通用提示，完整堆栈写日志
            logger.exception("LLM stream failed")
            yield f"data: {json.dumps({'error': '调用大模型失败，请稍后重试'}, ensure_ascii=False)}\n\n"

    # X-Accel-Buffering: no 让 Nginx 不缓冲，保证 SSE 实时推送到浏览器
    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
        from tencentcloud.tts.v20190823 import models, tts_client
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


@app.post("/asr")
def asr():
    """语音识别：前端上传 WAV 音频，腾讯云一句话识别返回文字。

    前端用 AudioContext 采集 16kHz 单声道 PCM 并封装 WAV 后上传，
    替代 Chrome 的 webkitSpeechRecognition（中国大陆连不上 Google 服务）。
    """
    # 先校验输入，再查配置（无 key 时空音频也应是 400 而非 501）
    # 支持 multipart 文件字段 audio，或直接 raw body
    audio_file = request.files.get("audio")
    if audio_file is not None:
        audio_bytes = audio_file.read()
    else:
        audio_bytes = request.get_data(cache=True)

    if not audio_bytes:
        return jsonify({"error": "audio 不能为空"}), 400
    if len(audio_bytes) > 4 * 1024 * 1024:  # 限制 4MB，一句话识别足够
        return jsonify({"error": "音频过大"}), 413

    if not TENCENT_SECRET_ID or not TENCENT_SECRET_KEY:
        return jsonify({"error": "ASR 未配置"}), 501

    try:
        from tencentcloud.asr.v20190614 import asr_client, models
        from tencentcloud.common import credential
        from tencentcloud.common.profile.client_profile import ClientProfile
        from tencentcloud.common.profile.http_profile import HttpProfile
        cred = credential.Credential(TENCENT_SECRET_ID, TENCENT_SECRET_KEY)
        http_profile = HttpProfile()
        http_profile.endpoint = "asr.tencentcloudapi.com"
        http_profile.reqTimeout = 10   # 腾讯云 API 超时 10s，避免 gunicorn worker 卡死
        client_profile = ClientProfile()
        client_profile.httpProfile = http_profile
        client = asr_client.AsrClient(cred, ASR_REGION, client_profile)

        req = models.SentenceRecognitionRequest()
        req.EngSerViceType = "16k_zh"     # 16k 中文普通话
        req.SourceType = 0                # 0=本地音频字节
        req.VoiceFormat = "wav"
        req.Data = base64.b64encode(audio_bytes).decode()
        req.DataLen = len(audio_bytes)
        resp = client.SentenceRecognition(req)
        return jsonify(text=resp.Result or "")
    except Exception as exc:
        # 调试期：把腾讯云真实错误透传给前端（detail 字段），便于定位卡点；
        # 定位完成后可去掉 detail，仅保留通用 error 文案。
        logger.exception("ASR request failed")
        return jsonify({"error": "语音识别失败，请稍后重试", "detail": str(exc)}), 502


def main() -> None:
    app.run(host="0.0.0.0", port=8000, debug=False)  # nosec B104: 对外服务需绑 0.0.0.0


if __name__ == "__main__":
    main()
