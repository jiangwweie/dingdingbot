# 盯盘狗 - 脚本工具目录

**更新日期**: 2026-03-31

## 📁 目录结构

```
scripts/
├── README.md              # 本文件
├── tools/                 # 工具脚本
│   ├── fix_filenames.py       # 文件名修复工具
│   ├── fix_unicode_paths.py   # Unicode 路径修复
│   ├── standardize_filenames.py # 文件名标准化
│   └── read_markdown.py       # Markdown 读取工具
├── data/                  # 数据脚本
│   └── backfill_7days.py      # K 线数据回补
├── deploy/                # 部署脚本
│   ├── deploy.sh              # 主部署脚本
│   ├── start.sh               # 启动服务
│   ├── stop.sh                # 停止服务
│   └── deploy-frontend.sh     # 前端部署
└── test/                  # 测试脚本
    ├── test_send_signal.py    # 信号推送测试
    └── test_send_styles.py    # 通知样式测试
```

---

## 🚀 快速启动

### 启动服务
```bash
# 使用默认端口（后端 8000, 前端 5173）
./scripts/deploy/start.sh

# 或指定端口
FRONTEND_PORT=3000 BACKEND_PORT=8080 ./scripts/deploy/start.sh
```

### 停止服务
```bash
./scripts/deploy/stop.sh
```

---

## 🛠️ 工具脚本

### 数据回补
```bash
# 回补最近 7 天的 K 线数据
python3 scripts/data/backfill_7days.py
```

### 文件名修复
```bash
# 修复 Unicode 文件名
python3 scripts/tools/fix_unicode_paths.py

# 标准化文件名
python3 scripts/tools/standardize_filenames.py
```

---

## 📝 日志查看

```bash
# 实时查看后端日志
tail -f logs/backend.log

# 实时查看前端日志
tail -f logs/frontend.log

# 查看最近 50 行
tail -50 logs/backend.log
```

---

## 🛠️ 故障排查

### 后端启动失败
```bash
# 查看详细日志
tail -100 logs/backend.log

# 检查端口占用
lsof -ti:8000

# 手动启动调试
source venv/bin/activate
python3 -m src.main
```

### 前端启动失败
```bash
# 查看详细日志
tail -100 logs/frontend.log

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
| `scripts/deploy/start.sh` | 启动服务 |
| `scripts/deploy/stop.sh` | 停止服务 |
| `scripts/tools/fix_filenames.py` | 文件名修复 |
| `scripts/data/backfill_7days.py` | 数据回补 |
| `.backend.pid` | 后端进程 ID |
| `.frontend.pid` | 前端进程 ID |
| `logs/backend.log` | 后端日志 |
| `logs/frontend.log` | 前端日志 |
| `.env` | 可选的端口配置 |

---

## ⚙️ 端口配置

### 方法 1：命令行指定
```bash
FRONTEND_PORT=3000 BACKEND_PORT=8080 ./scripts/deploy/start.sh
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
4. **graceful shutdown** - 停止时先发送 TERM 信号，等待 1 秒后强制 kill

---

## 💡 提示

- 使用 `Ctrl+C` 只能停止前台进程，后台进程需要用 `./scripts/deploy/stop.sh` 停止
- 重启电脑后，残留的 PID 文件会被自动清理（进程不存在时）
- 查看当前运行的服务：`ps aux | grep -E "python3.*main|npm.*dev|vite"`
