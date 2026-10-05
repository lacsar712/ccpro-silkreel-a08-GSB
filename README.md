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
| `admin` | `123456` | 管理员 |
| `worker` | `123456` | 缫丝工 |

## 业务规则

- 盆状态不可标成「已缫完」，除非该盆**最近一条**汤温记录落在 **38～42℃**。规则在 `backend/app/services.py`。
- 「缫丝中」改回「浸茧」时，该坞**当天**须有一条**未作废**且余氯 **≥ 0.3 毫克/升**的清汤记录；无记录或余氯不足均以中文提示挡住。登记汤温、标已缫完、从已缫完拨浸茧均不读余氯。
- 清汤余氯记录字段：坞、余氯值（毫克/升，须为正数）、采样时刻、采样人、可空的作废时刻；同一坞同一自然日**至多一条未作废记录**（数据库部分唯一索引兜底，并发双交只留一条）。
- 仅管理员可采样与作废；顶栏可在「环盆作业台」与「清汤余氯」之间切换，余氯专页按日列出、新建、作废。

## 快速启动

```bash
cd SilkReel/SilkReel-01
docker compose up --build
```
