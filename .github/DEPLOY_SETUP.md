# 部署前置配置（一次性）

本工作流通过 SSH 把代码同步到云服务器并重启服务。首次使用请完成以下三步。

## 1. 生成部署专用 SSH 密钥对

在本地（或任意安全机器）生成一对密钥，**不要**设置密码短语：

```bash
ssh-keygen -t ed25519 -f deploy_key -N ""
```

- 公钥 `deploy_key.pub` 加入服务器的 `~/.ssh/authorized_keys`
- 私钥 `deploy_key` 的完整内容（含 `-----BEGIN/END-----` 头尾）配置到 GitHub Secret **SSH_KEY**

## 2. 在 GitHub 配置 Secrets

路径：仓库 **Settings → Secrets and variables → Actions → New repository secret**

| Secret 名称     | 示例值            | 说明                         |
| --------------- | ----------------- | ---------------------------- |
| `SSH_HOST`      | `1.2.3.4`         | 服务器公网 IP 或域名         |
| `SSH_PORT`      | `22`              | SSH 端口（默认 22，可选）    |
| `SSH_USERNAME`  | `deploy`          | 登录用户名（建议专用账号）   |
| `SSH_KEY`       | （私钥全文）      | 上一步生成的私钥内容         |

> 建议为部署单独建一个低权限账号（如 `deploy`），并仅授权其所需目录与服务。

## 3. 服务器端准备（一键脚本）

仓库已提供 `scripts/server-init.sh`，拷到服务器上以 root 运行即可自动完成：

- 安装 `python3` / `venv` / `rsync`
- 创建 `deploy` 账号和 `/var/www/app` 部署目录
- 写入 `myapp.service`（systemd）并设为开机自启
- 配置免密 `systemctl restart` 权限
- 传入公钥时自动写入 `~/.ssh/authorized_keys`

```bash
# 在服务器上执行（公钥参数可选）：
sudo bash server-init.sh "$(cat deploy_key.pub)"
```

若改用 Docker，请在服务器放置 `docker-compose.yml`，并把 `ci-cd.yml` 远程脚本中的重启方式改为方式 B。

## 调整触发分支 / 部署目录

- 触发分支：`on.push.branches` 与 `on.pull_request.branches`
- 部署目录与服务名：`ci-cd.yml` 顶部 `env` 中的 `DEPLOY_PATH`、`SERVICE_NAME`
- 测试矩阵版本：`jobs.test.strategy.matrix.python-version`
