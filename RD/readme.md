# RD FastAPI 认证与用户数据服务

本目录提供前端 `FE` 所需的登录/注册/退出/登录态查询/用户资料图表接口。

## 目录结构

- `main.py`：FastAPI 服务装配与启动入口（中间件、路由挂载）
- `login/login.py`：登录/注册/退出/状态/用户资料核心业务逻辑
- `data/users.json`：用户数据存储文件（首次启动自动创建）

## 运行环境

- Conda 环境：`RD`
- 已安装：`fastapi`
- 需要可执行：`uvicorn`
- Session 依赖：`itsdangerous`

如果未安装运行依赖：

```powershell
pip install uvicorn itsdangerous
```

## 启动方式

在项目根目录执行：

```powershell
conda activate RD
cd D:\Learning_of_wanshushan\TG\RD
uvicorn main:app --host 127.0.0.1 --port 3000 --reload
```

启动后服务地址：

- `http://127.0.0.1:3000`
- 文档：`http://127.0.0.1:3000/docs`

## 可选环境变量

- `RD_SESSION_SECRET`：Session 签名密钥（建议在生产环境设置）
- `RD_ALLOWED_ORIGINS`：允许跨域来源，逗号分隔

示例：

```powershell
$env:RD_SESSION_SECRET = "replace-with-a-strong-secret"
$env:RD_ALLOWED_ORIGINS = "http://127.0.0.1:4321,http://127.0.0.1:3000"
```

## 接口清单

### 1) 查询登录状态

- `GET /api/auth/status`

返回示例：

```json
{
	"loggedIn": true,
	"username": "demo",
	"message": "ok"
}
```

### 2) 注册

- `POST /api/auth/register`

请求体：

```json
{
	"username": "demo",
	"password": "123456",
	"confirmPassword": "123456"
}
```

### 3) 登录

- `POST /api/auth/login`

请求体：

```json
{
	"username": "demo",
	"password": "123456"
}
```

### 4) 退出登录

- `POST /api/auth/logout`

### 5) 读取用户资料与图表

- `GET /api/user/profile`

返回示例：

```json
{
	"username": "demo",
	"bio": "你好，demo！欢迎使用灵·诊。",
	"avatar": "",
	"links": [],
	"charts": [
		{
			"id": "chart-1",
			"points": [
				{ "x": 1, "y": 35 },
				{ "x": 2, "y": 41 }
			]
		}
	]
}
```

## 联调说明

1. 先启动 `RD/main.py` 服务（端口 `3000`）。
2. 前端加载用户页时会先调用 `GET /api/auth/status`。
3. 若返回 `loggedIn=true`，前端会调用 `GET /api/user/profile`。
4. 登录注册页会调用登录与注册接口；用户页“退出登录”按钮会调用退出接口。
