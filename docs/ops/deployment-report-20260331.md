# 部署报告 - ATR 过滤器修复

**部署时间**: 2026-03-31
**版本**: v2 (commit: aa95f19)
**部署类型**: Bug 修复

---

## 📋 变更摘要

### 问题描述
回测信号 293 和 294 (ETH/USDT 1h) 波动率分别为 0.487% 和 0.465%，低于 ATR 过滤器要求的 0.5%，但仍然被生成。

### 根因分析
`src/domain/filter_factory.py:578` 中 ATR 过滤器的默认参数 `min_atr_ratio` 设置为 `Decimal("0.001")` (0.1%)，而非预期值 `Decimal("0.005")` (0.5%)。

当用户配置中 `params: {}` 为空对象时，使用默认值 0.1%，导致过滤器阈值过低。

### 修复内容

| 文件 | 变更 | 说明 |
|------|------|------|
| `src/domain/filter_factory.py` | `min_atr_ratio: 0.001 → 0.005` | ATR 默认阈值从 0.1% 提升至 0.5% |
| `.claude/team/devops-engineer/SKILL.md` | 新增 | 运维工程师角色技能文档 |
| `.claude/team/README.md` | 更新 | 添加 DevOps 角色到团队配置 |

---

## 🚀 部署步骤

### 阶段 1: 拉取最新代码

```bash
cd /usr/local/monitorDog/code
git fetch origin
git checkout v2
git pull origin v2

# 验证版本
COMMIT_HASH=$(git rev-parse HEAD)
echo "部署版本：$COMMIT_HASH"
```

### 阶段 2: 构建前端

```bash
cd /usr/local/monitorDog/code/web-front

# 安装依赖
npm ci

# 构建生产版本
npm run build

# 复制构建产物到挂载目录
mkdir -p /usr/local/monitorDog/build/dist
cp -r dist/* /usr/local/monitorDog/build/dist/
```

### 阶段 3: 备份数据库

```bash
mkdir -p /usr/local/monitorDog/data-prod/backups
cp /usr/local/monitorDog/data-prod/signals-prod.db \
   /usr/local/monitorDog/data-prod/backups/signals-prod.$(date +%Y%m%d-%H%M%S).db

# 验证备份
ls -lth /usr/local/monitorDog/data-prod/backups/ | head -3
```

### 阶段 4: 重启 Docker 容器

```bash
cd /usr/local/monitorDog

# 停止现有容器
docker-compose down

# 启动新容器
docker-compose up -d

# 等待容器启动
sleep 10
```

### 阶段 5: 健康检查

```bash
# 检查容器状态
docker-compose ps

# 检查 API 可用性
curl -f http://localhost:8000/api/health || {
    echo "API 不可用！"
    docker-compose logs --tail=100
    exit 1
}

# 查看最新日志
docker-compose logs --tail=30
```

### 阶段 6: 验证 ATR 过滤器

```bash
# 检查日志中 ATR 过滤器拒绝记录
docker-compose logs | grep "ATR_FILTER_REJECTED" | tail -10

# 或查看日志文件
grep "ATR_FILTER_REJECTED" /usr/local/monitorDog/logs-prod/dingdingbot.log.* | tail -10
```

---

## ✅ 验证清单

- [ ] 容器状态正常 (`docker-compose ps` 显示 Up)
- [ ] API 健康检查通过 (`/api/health` 返回 200)
- [ ] 前端页面可访问 (`http://localhost:8000/`)
- [ ] ATR 过滤器日志正常
- [ ] 数据库备份完成

---

## 📊 预期效果

修复后，ATR 过滤器将正确拒绝波动率低于 0.5% 的信号：

- 信号 293 (0.487% 波动率) → 应被拒绝 ❌
- 信号 294 (0.465% 波动率) → 应被拒绝 ❌
- 波动率 ≥ 0.5% 的信号 → 正常通过 ✅

---

## 🔧 回滚方案

如需回滚到修复前版本：

```bash
cd /usr/local/monitorDog/code
git reset --hard 902dd06^  # 回退到上一个 commit
docker-compose restart
```

---

## 📝 备注

- 此修复仅影响新产生的信号
- 历史已生成的信号不会被修改
- 前端回测功能需手动添加 ATR 过滤器到策略配置

---

**部署人员**: DevOps Engineer
**审查人员**: Backend Dev + QA
