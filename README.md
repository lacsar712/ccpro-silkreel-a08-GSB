# SilkReel-01 · 江口缫丝坞

缫丝盆环状作业台。登录后看到的是沿汤池围成一圈的盆位，点盆登记汤温并改状态——不是侧栏双列表 CRUD。

## 技术栈

| 层 | 技术 |
| --- | --- |
| Web API | Quart（异步 Flask 族）· Hypercorn |
| 结构 | `repositories.py` 仓储 + `services.py` 门槛，路由不直接拼 SQL |
| 数据 | SQLAlchemy 2 async · asyncpg · PostgreSQL 15 |
| 前端 | Preact 10 · Vite |
| 部署 | Docker Compose |

## 路径与端口

- 前端：http://localhost:4760
- API：http://localhost:8760
- PostgreSQL：localhost:6160

## 演示账号

| 用户名 | 密码 | 角色 |
| --- | --- | --- |
| `admin` / `admin2` | `123456` | 管理员 |
| `worker` | `123456` | 缫丝工 |

## 业务规则

1. 盆状态不可标成「已缫完」，除非该盆**最近一条**汤温记录落在 **38～42℃**。规则在 `backend/app/services.py`。
2. **缫丝中改回浸茧**：该坞当天（按 `SITE_TIMEZONE`，默认 Asia/Shanghai 切自然日）须有一条**未作废**且**余氯 ≥ 0.3 毫克/升**的清汤记录；否则后端中文挡住。登记汤温、标已缫完、从已缫完拨浸茧均不读余氯。
3. 清汤余氯记录字段：坞、余氯值（必须为正数）、采样时刻、采样人、作废时刻（可空）。同一坞同一自然日**至多一条未作废记录**（行锁 + 数据库部分唯一索引双保险，两名值班交叉交两条只留一条）。
4. 仅**管理员**可采样与作废余氯记录（`POST /api/chlorine`、`POST /api/chlorine/{id}/void`，非管理员 403）；任何登录用户可在「清汤余氯」专页按日查看。

种子数据：甲-1 处于缫丝中，当天有一条余氯 **0.1** 毫克/升的记录（不足放行），需管理员先作废再重采合格记录后才能改回浸茧。

## 快速启动

```bash
cd SilkReel/SilkReel-01
docker compose up --build
```
