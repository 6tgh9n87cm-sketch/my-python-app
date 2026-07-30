#!/usr/bin/env bash
#
# server-init.sh — 云服务器一键初始化（Python + systemd 部署环境）
#
# 用法（先把这个脚本拷到服务器上）：
#   sudo bash server-init.sh                      # 仅初始化环境
#   sudo bash server-init.sh "<SSH 公钥内容>"      # 初始化并把公钥写入部署账号
#
# 完成后，把 ci-cd.yml 的 env 中 DEPLOY_PATH / SERVICE_NAME 与本脚本变量保持一致。
set -euo pipefail

# ================== 可配置变量（与 .github/workflows/ci-cd.yml 的 env 一致）==================
DEPLOY_USER="${DEPLOY_USER:-deploy}"
DEPLOY_PATH="${DEPLOY_PATH:-/var/www/app}"
SERVICE_NAME="${SERVICE_NAME:-myapp}"
APP_PORT="${APP_PORT:-8000}"
# 服务启动命令，按你的框架二选一/自行修改：
#   Flask / WSGI  : ${DEPLOY_PATH}/.venv/bin/gunicorn -w 2 -b 0.0.0.0:${APP_PORT} app:app
#   FastAPI / ASGI: ${DEPLOY_PATH}/.venv/bin/uvicorn main:app --host 0.0.0.0 --port ${APP_PORT}
EXEC_START="${EXEC_START:-${DEPLOY_PATH}/.venv/bin/gunicorn -w 2 -b 0.0.0.0:${APP_PORT} app:app}"
PUBKEY="${1:-}"

# ================== 0. 前置检查 ==================
if [ "$(id -u)" -ne 0 ]; then
  echo "错误：请以 root 运行，例如：sudo bash server-init.sh" >&2
  exit 1
fi

# ================== 1. 安装系统依赖 ==================
echo "[1/6] 安装系统依赖..."
if command -v apt-get >/dev/null 2>&1; then
  apt-get update -y
  DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-venv python3-pip rsync sudo
elif command -v yum >/dev/null 2>&1; then
  yum install -y python3 python3-pip rsync sudo
else
  echo "未识别的包管理器，请手动安装 python3 / venv / rsync / sudo" >&2
  exit 1
fi

# ================== 2. 创建部署账号 ==================
echo "[2/6] 创建部署账号 $DEPLOY_USER ..."
if ! id "$DEPLOY_USER" >/dev/null 2>&1; then
  useradd -m -s /bin/bash "$DEPLOY_USER"
fi

# ================== 3. 创建部署目录 ==================
echo "[3/6] 创建部署目录 $DEPLOY_PATH ..."
mkdir -p "$DEPLOY_PATH"
chown -R "$DEPLOY_USER:$DEPLOY_USER" "$DEPLOY_PATH"

# ================== 4. 写入 systemd 服务 ==================
echo "[4/6] 写入 systemd 服务 ${SERVICE_NAME}.service ..."
cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=${SERVICE_NAME} (deployed via GitHub Actions)
After=network.target

[Service]
User=${DEPLOY_USER}
WorkingDirectory=${DEPLOY_PATH}
ExecStart=${EXEC_START}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"

# ================== 5. 配置免密重启权限 ==================
echo "[5/6] 配置 $DEPLOY_USER 免密重启 $SERVICE_NAME ..."
SUDOERS_FILE="/etc/sudoers.d/${SERVICE_NAME}-restart"
cat > "$SUDOERS_FILE" <<EOF
${DEPLOY_USER} ALL=(root) NOPASSWD: /bin/systemctl restart ${SERVICE_NAME}, /usr/bin/systemctl restart ${SERVICE_NAME}, /bin/systemctl status ${SERVICE_NAME}, /usr/bin/systemctl status ${SERVICE_NAME}
EOF
chmod 440 "$SUDOERS_FILE"
visudo -cf "$SUDOERS_FILE" >/dev/null

# ================== 6. 写入 SSH 公钥（可选）==================
if [ -n "$PUBKEY" ]; then
  echo "[6/6] 写入 $DEPLOY_USER 的 SSH 公钥 ..."
  SSH_DIR="/home/${DEPLOY_USER}/.ssh"
  mkdir -p "$SSH_DIR"
  echo "$PUBKEY" >> "$SSH_DIR/authorized_keys"
  chmod 700 "$SSH_DIR"
  chmod 600 "$SSH_DIR/authorized_keys"
  chown -R "$DEPLOY_USER:$DEPLOY_USER" "$SSH_DIR"
else
  echo "[6/6] 未提供公钥，跳过（稍后执行：sudo bash server-init.sh \"\$(cat deploy_key.pub)\"）"
fi

cat <<MSG
====================================================================
✅ 初始化完成

下一步：
1. 在本地生成部署密钥：ssh-keygen -t ed25519 -f deploy_key -N ""
2. 若刚才没传公钥，执行：sudo bash server-init.sh "\$(cat deploy_key.pub)"
3. 把私钥 deploy_key 全文配到 GitHub Secret：SSH_KEY
4. 确保 requirements.txt 含 gunicorn（或 uvicorn），否则服务起不来
5. 首次部署后服务才会真正启动（CI 的 systemctl restart 会自动拉起）
====================================================================
MSG
