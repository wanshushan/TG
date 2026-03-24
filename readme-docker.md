# TG 项目 Docker 使用说明

本文档覆盖三类场景：

- 开发期代码同步（容器内热重载）
- 启动 Docker 中的前后端服务（生产运行方式）
- 镜像打包与导出（便于分发部署）

---

## 1. 前置要求

- 已安装 Docker Desktop（Windows）
- 已启用 Compose V2（`docker compose`）
- 在项目根目录执行命令（即包含 `docker-compose.yml` 的目录）

可先检查：

```powershell
docker --version
docker compose version
```

---

## 2. 生产方式启动（推荐）

使用文件：`docker-compose.yml`

### 2.1 构建并启动

```powershell
docker compose up -d --build
```

访问地址：

- 前端：`http://127.0.0.1:4321`
- 后端：`http://127.0.0.1:3000`

### 2.2 查看状态与健康检查

```powershell
docker compose ps
docker inspect --format "{{.Name}} => {{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}" tg-rd tg-fe
```

说明：

- 本项目已在 compose 中配置 `healthcheck`
- 前端 `fe` 会等待后端 `rd` 健康后再启动

### 2.3 查看日志

```powershell
docker compose logs -f
```

仅看某个服务：

```powershell
docker compose logs -f rd
docker compose logs -f fe
```

### 2.4 停止与清理

```powershell
docker compose down
```

保留镜像仅删除容器/网络；若要额外删除未使用镜像可手动执行：

```powershell
docker image prune -f
```

---

## 3. 开发方式（代码同步 + 热重载）

使用文件：`docker-compose.dev.yml`

该模式特点：

- `RD` 目录挂载到容器内 `/app`，后端使用 `uvicorn --reload`
- `FE` 目录挂载到容器内 `/app`，前端使用 `pnpm dev`
- 改代码后浏览器自动看到最新效果（根据框架刷新策略）

### 3.1 启动开发容器

```powershell
docker compose -f docker-compose.dev.yml up -d --build
```

### 3.2 开发期查看日志

```powershell
docker compose -f docker-compose.dev.yml logs -f
```

### 3.3 开发期停止

```powershell
docker compose -f docker-compose.dev.yml down
```

### 3.4 说明

- 前端首次启动会在容器内执行 `pnpm install`，因此第一次会慢一些
- 前端依赖目录使用命名卷 `tg-fe-node-modules`，避免宿主机与容器依赖冲突

---

## 4. 环境变量与安全建议

关键变量：

- `RD_SESSION_SECRET`：请改为强随机字符串
- `RD_ALLOWED_ORIGINS`：按你的域名/端口白名单设置
- `RD_BACKEND_BASE_URL`：前端代理到后端的容器地址（生产 compose 中默认 `http://rd:3000`）

建议：

- 生产环境不要保留默认 `change-this-to-a-strong-secret`
- 若使用公网域名，建议再加 Nginx/Caddy 反向代理与 HTTPS

---

## 5. 镜像打包（构建、打标签、导出）

### 5.1 直接通过 compose 构建

```powershell
docker compose build
```

构建后本地镜像名通常为：

- `tg-rd:latest`
- `tg-fe:latest`

### 5.2 给镜像打标签

```powershell
docker tag tg-rd:latest yourname/tg-rd:1.0.0
docker tag tg-fe:latest yourname/tg-fe:1.0.0
```

### 5.3 导出镜像为 tar 包

```powershell
docker save -o tg-rd_1.0.0.tar yourname/tg-rd:1.0.0
docker save -o tg-fe_1.0.0.tar yourname/tg-fe:1.0.0
```

### 5.4 从 tar 包导入

```powershell
docker load -i tg-rd_1.0.0.tar
docker load -i tg-fe_1.0.0.tar
```

### 5.5 推送到镜像仓库（可选）

```powershell
docker login
docker push yourname/tg-rd:1.0.0
docker push yourname/tg-fe:1.0.0
```

---

## 6. 常见问题排查

### 6.1 容器一直重启

```powershell
docker compose ps
docker compose logs -f fe
docker compose logs -f rd
```

### 6.2 端口占用

如果 `3000` 或 `4321` 被占用，修改 compose 中 `ports` 左侧宿主机端口即可。

### 6.3 强制重建

```powershell
docker compose down
docker compose build --no-cache
docker compose up -d
```

---

## 7. 一键脚本（PowerShell）

项目根目录提供 `start-docker.ps1` 和 `stop-docker.ps1`，用于统一管理生产/开发 Docker 启停。

### 7.1 生产模式

```powershell
./start-docker.ps1
./start-docker.ps1 -Mode prod -Action up -Build
./start-docker.ps1 -Mode prod -Action ps
./start-docker.ps1 -Mode prod -Action logs -Follow
./start-docker.ps1 -Mode prod -Action down
./stop-docker.ps1 -Mode prod
```

### 7.2 开发模式（同步 + 热重载）

```powershell
./start-docker.ps1 -Mode dev -Action up -Build
./start-docker.ps1 -Mode dev -Action ps
./start-docker.ps1 -Mode dev -Action logs -Follow
./start-docker.ps1 -Mode dev -Action down
./stop-docker.ps1 -Mode dev
```

### 7.3 支持的参数

- `-Mode`: `prod` 或 `dev`（默认 `prod`）
- `-Action`: `up` / `down` / `logs` / `ps` / `restart` / `rebuild`
- `-Build`: 仅 `up` 时生效，等价于 `docker compose up -d --build`
- `-Follow`: 仅 `logs` 时生效，等价于 `docker compose logs -f`

`stop-docker.ps1` 支持参数：

- `-Mode`: `prod` 或 `dev`（默认 `prod`）
- `-RemoveVolumes`: 等价于 `docker compose down -v`
- `-RemoveOrphans`: 等价于 `docker compose down --remove-orphans`

