# tOS Quality Workbench 部署指南

## 环境要求

- Python 3.11+
- Node.js 20+ (前端构建)
- Docker & Docker Compose (推荐)

## 快速部署

### 1. 使用 Docker Compose（推荐）

```bash
# 1. 复制环境变量配置
cp .env.example .env

# 2. 编辑 .env 文件，填写飞书应用配置
vim .env

# 3. 启动服务
docker-compose up -d

# 4. 查看日志
docker-compose logs -f
```

### 2. 手动部署

```bash
# 1. 安装后端依赖
cd backend
pip install -r requirements.txt

# 2. 安装前端依赖并构建
cd ../frontend
npm install
npm run build

# 3. 复制环境变量配置
cd ..
cp .env.example .env

# 4. 编辑 .env 文件
vim .env

# 5. 启动后端
cd backend
python run.py
```

## 环境变量说明

| 变量名 | 必填 | 默认值 | 说明 |
|--------|------|--------|------|
| `FEISHU_APP_ID` | 否 | 空 | 飞书应用 ID |
| `FEISHU_APP_SECRET` | 否 | 空 | 飞书应用密钥 |
| `HOST` | 否 | `0.0.0.0` | 监听地址 |
| `PORT` | 否 | `8000` | 监听端口 |
| `CORS_ORIGINS` | 否 | `http://localhost:3000,http://localhost:5173` | 允许的跨域来源（逗号分隔） |
| `VERIFY_SSL` | 否 | `false` | 是否验证 SSL 证书 |
| `DEBUG` | 否 | `false` | 是否启用调试模式 |

## 安全配置

### 生产环境建议

1. **CORS 配置**：设置为具体域名
   ```bash
   CORS_ORIGINS=https://your-domain.com
   ```

2. **SSL 证书验证**：启用
   ```bash
   VERIFY_SSL=true
   ```

3. **调试模式**：关闭
   ```bash
   DEBUG=false
   ```

4. **数据备份**：定期备份 `/data/.tos_quality_workbench` 目录

## 访问地址

- 后端 API：`http://your-server:8000`
- 健康检查：`http://your-server:8000/api/health`
- API 文档：`http://your-server:8000/docs`

## 常见问题

### 1. 飞书功能不可用

检查 `.env` 文件中的 `FEISHU_APP_ID` 和 `FEISHU_APP_SECRET` 是否正确配置。

### 2. 数据库文件位置

默认在 `~/.tos_quality_workbench/tos_quality.db`，Docker 部署时在 `/data/.tos_quality_workbench/`。

### 3. 如何更新

```bash
# Docker 部署
docker-compose down
docker-compose build
docker-compose up -d

# 手动部署
git pull
cd frontend && npm install && npm run build
cd ../backend && pip install -r requirements.txt
# 重启后端服务
```
