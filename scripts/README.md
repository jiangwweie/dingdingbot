# 盯盘狗 - 快速启动指南

## 🚀 快速命令

### 启动服务
```bash
# 使用默认端口（后端 8000, 前端 5173）
./scripts/start.sh

# 或指定端口
FRONTEND_PORT=3000 BACKEND_PORT=8080 ./scripts/start.sh
```

### 停止服务
```bash
./scripts/stop.sh
```

### 重启服务
```bash
./scripts/stop.sh && ./scripts/start.sh
```

---

## 📋 启动脚本功能

### `start.sh` 做了什么：

1. **加载配置** - 读取 `.env` 文件中的端口配置
2. **停止旧服务** - 自动调用 `stop.sh` 清理
3. **启动后端** - 运行 `python3 -m src.main`
   - 激活虚拟环境（如果存在）
   - 写入 PID 到 `.backend.pid`
   - 等待健康检查通过
4. **启动前端** - 运行 `npm run dev`
   - 写入 PID 到 `.frontend.pid`
   - 等待服务可访问

### `stop.sh` 做了什么：

1. **停止后端** - 读取 `.backend.pid` 并终止进程
2. **停止前端** - 读取 `.frontend.pid` 并终止进程及子进程
3. **清理端口** - 确保 8000 和 5173 端口被释放
4. **清理残留** - 清除可能的 uvicorn/vite 残留进程

---

## 🔍 日志查看

```bash
# 实时查看后端日志
tail -f backend.log

# 实时查看前端日志
tail -f frontend.log

# 查看最近 50 行
tail -50 backend.log
```

---

## 🛠️ 故障排查

### 后端启动失败
```bash
# 查看详细日志
tail -100 backend.log

# 检查端口占用
lsof -ti:8000

# 手动启动调试
source venv/bin/activate
python3 -m src.main
```

### 前端启动失败
```bash
# 查看详细日志
tail -100 frontend.log

# 检查端口占用
lsof -ti:5173

# 手动启动调试
cd web-front
npm run dev
```

### 服务停止后端口仍被占用
```bash
# 强制清理端口
for PORT in 8000 5173; do
    lsof -ti:$PORT | xargs kill -9
done
```

---

## 📁 相关文件

| 文件 | 说明 |
|------|------|
| `scripts/start.sh` | 启动脚本 |
| `scripts/stop.sh` | 停止脚本 |
| `.backend.pid` | 后端进程 ID |
| `.frontend.pid` | 前端进程 ID |
| `backend.log` | 后端日志 |
| `frontend.log` | 前端日志 |
| `.env` | 可选的端口配置 |

---

## ⚙️ 端口配置

### 方法 1：命令行指定
```bash
FRONTEND_PORT=3000 BACKEND_PORT=8080 ./scripts/start.sh
```

### 方法 2：创建 `.env` 文件
```bash
# .env
FRONTEND_PORT=3000
BACKEND_PORT=8080
```

### 默认端口
- 后端：8000
- 前端：5173

---

## 🔐 注意事项

1. **脚本不会报错退出** - 即使服务未运行或端口被占用，脚本也会尝试清理并继续
2. **自动清理残留进程** - 如果 PID 文件存在但进程已死，会自动清理
3. **健康检查** - 启动脚本会等待服务就绪后才返回
4. ** graceful shutdown** - 停止时先发送 TERM 信号，等待 1 秒后强制 kill

---

## 💡 提示

- 使用 `Ctrl+C` 只能停止前台进程，后台进程需要用 `./scripts/stop.sh` 停止
- 重启电脑后，残留的 PID 文件会被自动清理（进程不存在时）
- 查看当前运行的服务：`ps aux | grep -E "python3.*main|npm.*dev|vite"`
