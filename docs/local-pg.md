# 本地 PostgreSQL 开发环境

## 启动

```bash
docker compose -f docker-compose.pg.yml up -d
```

## 连接串

```
PG_DATABASE_URL=postgresql+asyncpg://dingdingbot:dingdingbot_dev@localhost:5432/dingdingbot
```

在 `.env` 中取消注释即可启用。

## 停止

```bash
docker compose -f docker-compose.pg.yml down
```

## 清理数据（重置数据库）

```bash
docker compose -f docker-compose.pg.yml down -v
```

## 连接信息

| 项目 | 值 |
|------|-----|
| Host | localhost |
| Port | 5432 |
| Database | dingdingbot |
| User | dingdingbot |
| Password | dingdingbot_dev |

## CLI 连接

```bash
docker exec -it dingdingbot-pg psql -U dingdingbot -d dingdingbot
```
