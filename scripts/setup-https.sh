#!/usr/bin/env bash
#
# setup-https.sh — 给已部署的 Flask 应用加 HTTPS（nginx 反向代理 + Let's Encrypt 免费证书）
#
# 前置条件：
#   1. 已按 server-init.sh 部署好 myapp（gunicorn 在 8000 端口）
#   2. 你已购买域名，并把 A 记录指向服务器公网 IP（124.220.216.238）
#   3. 腾讯云安全组已放行 80、443 端口
#   4. 以 root 运行本脚本： sudo bash setup-https.sh 你的域名
#
# 例： sudo bash setup-https.sh nova.example.top
set -euo pipefail

DOMAIN="${1:-}"
if [ -z "$DOMAIN" ]; then
  echo "用法：sudo bash setup-https.sh 你的域名" >&2
  exit 1
fi
if [ "$(id -u)" -ne 0 ]; then
  echo "错误：请以 root 运行（sudo bash setup-https.sh ...）" >&2
  exit 1
fi

DEPLOY_PATH="${DEPLOY_PATH:-/var/www/app}"
SERVICE_NAME="${SERVICE_NAME:-myapp}"
APP_PORT="${APP_PORT:-8000}"

echo "==> 目标域名：$DOMAIN  |  代理到 127.0.0.1:${APP_PORT}"

# ---------- 1. 安装 nginx + certbot ----------
echo "[1/5] 安装 nginx 与 certbot ..."
apt-get update -y
DEBIAN_FRONTEND=noninteractive apt-get install -y nginx certbot python3-certbot-nginx

# ---------- 2. 让 gunicorn 只监听本机（更安全，仅 nginx 能访问）----------
echo "[2/5] 收口 gunicorn 到 127.0.0.1 ..."
SYSTEMD_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
if [ -f "$SYSTEMD_FILE" ]; then
  sed -i "s#-b 0.0.0.0:${APP_PORT}#-b 127.0.0.1:${APP_PORT}#g" "$SYSTEMD_FILE"
  systemctl daemon-reload
  systemctl restart "${SERVICE_NAME}"
  sleep 2
  systemctl is-active --quiet "${SERVICE_NAME}" && echo "    myapp 已重启并仅监听本机" || echo "    ⚠️ myapp 未正常启动，请检查"
fi

# ---------- 3. 写 nginx 站点配置（HTTP，certbot 随后会自动加 HTTPS）----------
echo "[3/5] 写入 nginx 站点配置 ..."
cat > "/etc/nginx/sites-available/${DOMAIN}" <<EOF
server {
    listen 80;
    server_name ${DOMAIN} www.${DOMAIN};

    location / {
        proxy_pass http://127.0.0.1:${APP_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
ln -sf "/etc/nginx/sites-available/${DOMAIN}" "/etc/nginx/sites-enabled/${DOMAIN}"
# 关闭默认站点，避免冲突
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx && echo "    nginx 已启动（HTTP）"

# ---------- 4. 申请免费证书并自动开启 HTTPS ----------
echo "[4/5] 申请 Let's Encrypt 证书（会自动把 80 跳转 443）..."
certbot --nginx -d "${DOMAIN}" -d "www.${DOMAIN}" \
  --non-interactive --agree-tos -m "admin@${DOMAIN}" \
  --redirect --no-eff-email

# ---------- 5. 验证自动续期 ----------
echo "[5/5] 配置证书自动续期 ..."
systemctl enable certbot.timer 2>/dev/null || true
certbot renew --dry-run && echo "    续期测试通过 ✅"

cat <<MSG
====================================================================
✅ HTTPS 部署完成！

现在访问： https://${DOMAIN}
（麦克风/语音对话在 HTTPS 下可用）

说明：
- 证书 90 天有效，certbot 会自动续期，无需手动操作
- 如需改回 gunicorn 监听公网，编辑 ${SYSTEMD_FILE} 的 ExecStart 即可
- 部署代码仍走 GitHub Actions，push 后自动重启 myapp
====================================================================
MSG
