"""示例 Flask 应用：可被 gunicorn 作为 WSGI 入口加载（app:app）。

提供三个端点：
  GET /        首页（返回欢迎信息）
  GET /health  健康检查端点
  GET /add     简单计算示例（?a=1&b=2）

部署方式：
  gunicorn -w 2 -b 0.0.0.0:8000 app:app
"""

from flask import Flask, jsonify, request

app = Flask(__name__)


@app.get("/")
def index() -> dict:
    """首页：返回服务信息和版本。"""
    return {
        "service": "my-python-app",
        "version": "0.1.0",
        "message": "Hello from GitHub Actions CI/CD!",
    }


@app.get("/health")
def health() -> dict:
    """健康检查端点（k8s / 负载均衡常用）。"""
    return {"status": "ok"}


@app.get("/add")
def add() -> dict:
    """计算两个整数之和：/add?a=1&b=2"""
    try:
        a = int(request.args.get("a", 0))
        b = int(request.args.get("b", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "a and b must be integers"}), 400
    return {"result": a + b}


def main() -> None:
    """本地开发运行入口。"""
    app.run(host="0.0.0.0", port=8000, debug=False)


if __name__ == "__main__":
    main()