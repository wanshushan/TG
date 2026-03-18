# 用户中心与认证接口约定（RD API）

本文给后端用于对接前端以下页面：

- 用户页：`/user`
- 登录注册页：`/auth`

前端实现方式：
- **先调用登录状态接口**判断是否已登录。
- 已登录：读取用户资料与图表 API。
- 未登录：使用前端本地默认数据。

---

## 1. 前端已配置的接口地址

配置文件：`FE/src/config.ts`，字段在 `USER_PROFILE_CONFIG.auth` 与 `USER_PROFILE_CONFIG.api`。

### 认证相关
- `statusEndpoint`: `http://127.0.0.1:3000/api/auth/status`
- `loginEndpoint`: `http://127.0.0.1:3000/api/auth/login`
- `registerEndpoint`: `http://127.0.0.1:3000/api/auth/register`
- `logoutEndpoint`: `http://127.0.0.1:3000/api/auth/logout`

### 用户资料与图表
- `endpoint`: `http://127.0.0.1:3000/api/user/profile`

---

## 2. 通用约定（必须）

1. 所有接口返回 `application/json`。
2. 登录态基于 **Cookie Session**（推荐 `HttpOnly` + `Secure` + `SameSite`）。
3. 前端请求已带 `credentials: include`，后端需允许携带 Cookie：
   - 若跨域，需正确配置 CORS 与 `Access-Control-Allow-Credentials: true`。
4. 错误时建议返回统一结构：

```json
{
  "success": false,
  "message": "错误原因"
}
```

---

## 3. 认证接口

## 3.1 登录状态查询

- Method: `GET`
- URL: `/api/auth/status`
- 用途：前端判断是否登录，从而切换数据源。

### 成功响应（已登录）

```json
{
  "loggedIn": true,
  "username": "wanshushan",
  "message": "ok"
}
```

### 成功响应（未登录）

```json
{
  "loggedIn": false,
  "username": "",
  "message": "not logged in"
}
```

### 状态码
- `200`: 成功返回登录状态。
- 不建议对未登录返回 `401`，建议仍返回 `200 + loggedIn:false`，便于前端统一处理。

---

## 3.2 登录

- Method: `POST`
- URL: `/api/auth/login`
- Body:

```json
{
  "username": "demo",
  "password": "123456"
}
```

### 成功响应

```json
{
  "success": true,
  "message": "登录成功",
  "username": "demo"
}
```

> 登录成功后后端需写入会话 Cookie。

### 失败响应示例

```json
{
  "success": false,
  "message": "用户名或密码错误"
}
```

### 状态码建议
- `200`: 登录成功。
- `400`: 参数校验失败。
- `401`: 凭据错误。
- `500`: 服务异常。

---

## 3.3 注册

- Method: `POST`
- URL: `/api/auth/register`
- Body:

```json
{
  "username": "demo",
  "password": "123456",
  "confirmPassword": "123456"
}
```

### 成功响应

```json
{
  "success": true,
  "message": "注册成功"
}
```

### 失败响应示例

```json
{
  "success": false,
  "message": "用户名已存在"
}
```

### 状态码建议
- `200`: 注册成功。
- `400`: 参数校验失败（例如两次密码不一致）。
- `409`: 用户名冲突。
- `500`: 服务异常。

---

## 3.4 退出登录

- Method: `POST`
- URL: `/api/auth/logout`
- Body: 可空

### 成功响应

```json
{
  "success": true,
  "message": "已退出登录"
}
```

> 后端需清理会话并使 Cookie 失效。

### 状态码建议
- `200`: 成功（即使原本未登录，也可返回成功，幂等更友好）。
- `500`: 服务异常。

---

## 4. 用户资料与图表接口

## 4.1 用户资料+四图数据

- Method: `GET`
- URL: `/api/user/profile`
- 前置：已登录（通过 Session Cookie 识别）

### 成功响应（推荐）

```json
{
  "username": "wanshushan",
  "bio": "A blog about life and code.",
  "avatar": "https://example.com/avatar.png",
  "links": [
    {
      "name": "GitHub",
      "href": "https://github.com/wanshushan",
      "icon": "fa6-brands:github"
    }
  ],
  "charts": [
    {
      "id": "chart-1",
      "points": [
        { "x": 1, "y": 35 },
        { "x": 2, "y": 41 },
        { "x": 3, "y": 38 },
        { "x": 4, "y": 46 }
      ]
    },
    {
      "id": "chart-2",
      "points": [
        { "x": 1, "y": 22 },
        { "x": 2, "y": 26 },
        { "x": 3, "y": 31 },
        { "x": 4, "y": 29 }
      ]
    },
    {
      "id": "chart-3",
      "points": [
        { "x": 1, "y": 60 },
        { "x": 2, "y": 54 },
        { "x": 3, "y": 57 },
        { "x": 4, "y": 63 }
      ]
    },
    {
      "id": "chart-4",
      "points": [
        { "x": 1, "y": 14 },
        { "x": 2, "y": 17 },
        { "x": 3, "y": 16 },
        { "x": 4, "y": 21 }
      ]
    }
  ]
}
```

### 兼容响应（`data` 包裹）

```json
{
  "data": {
    "username": "wanshushan",
    "bio": "A blog about life and code.",
    "avatar": "https://example.com/avatar.png",
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
}
```

### 字段说明
- `username`: 用户名（空值时前端回退本地默认 `User`）
- `bio`: 用户简介
- `avatar`: 头像 URL
- `links`: 社交链接（当前用户页已不展示，但可继续返回）
- `charts`: 四个折线图点位数据
  - `id`: 图表 ID（`chart-1` ~ `chart-4`，与前端配置匹配）
  - `points`: 点位数组
    - `x`: 横轴数值
    - `y`: 纵轴数值

> 横纵轴显示名称由前端配置 `USER_CHART_DEFINITIONS` 控制，不由后端返回。

### 状态码建议
- `200`: 成功。
- `401`: 未登录或会话失效（前端将自动回退本地数据，并显示登录入口）。
- `500`: 服务异常。

---

## 5. 前端行为说明（后端需知）

1. 用户页加载顺序：
   - 先 `GET /api/auth/status`
   - `loggedIn=true` 时再请求 `GET /api/user/profile`
   - `loggedIn=false` 时不会请求用户资料接口，直接显示本地默认数据
2. 用户页按钮：
   - 未登录：显示“登录/注册”，跳转 `/auth`
   - 已登录：显示“退出登录”，点击调用 `POST /api/auth/logout`
3. 登录注册页：
   - 登录表单调用 `POST /api/auth/login`
   - 注册表单调用 `POST /api/auth/register`

---

## 6. 联调检查清单

1. `/api/auth/status` 可正确返回 `loggedIn`。
2. 登录后浏览器中存在有效会话 Cookie。
3. `/api/user/profile` 在已登录时返回用户资料与 `charts`。
4. 未登录访问 `/user` 时应展示本地默认资料且仍显示四个图（回退数据）。
5. `/auth` 页面可完成登录、注册、退出全流程联调。
