import { render } from "preact";
import { useEffect, useState } from "preact/hooks";
import { api, clearToken, setToken, token } from "./api.js";
import "./app.css";

const STATUS_LABEL = { soaking: "浸茧", reeling: "缫丝中", reeled: "已缫完" };
const MIN_CHLORINE = 0.3;

function Login({ onOk }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("123456");
  const [err, setErr] = useState("");
  async function submit(e) {
    e.preventDefault();
    setErr("");
    try {
      const data = await api("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      setToken(data.access_token);
      onOk(data.user);
    } catch (ex) {
      setErr(ex.message);
    }
  }
  return (
    <div class="login">
      <h1>江口缫丝坞</h1>
      <p>汤温环盆作业台，不是列表台账。</p>
      <form onSubmit={submit} autocomplete="off">
        <label>
          用户名
          <input name="username" autocomplete="off" value={username} onInput={(e) => setUsername(e.target.value)} />
        </label>
        <label>
          密码
          <input name="password" type="password" autocomplete="off" value={password} onInput={(e) => setPassword(e.target.value)} />
        </label>
        <p class="hint">已预填 admin / 123456，另有 worker / 123456</p>
        <button type="submit">登录</button>
      </form>
      {err && <p class="err">{err}</p>}
    </div>
  );
}

function TopBar({ title, subtitle, view, setView, onLogout }) {
  return (
    <div class="topbar">
      <div>
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>
      <nav>
        <button class={view === "yard" ? "active" : ""} onClick={() => setView("yard")}>
          环盆作业台
        </button>
        <button class={view === "chlorine" ? "active" : ""} onClick={() => setView("chlorine")}>
          清汤余氯
        </button>
        <button onClick={onLogout}>退出</button>
      </nav>
    </div>
  );
}

function Yard({ user, view, setView, onLogout }) {
  const [board, setBoard] = useState(null);
  const [picked, setPicked] = useState(null);
  const [temp, setTemp] = useState("40");
  const [err, setErr] = useState("");

  async function refresh() {
    const data = await api("/api/board");
    setBoard(data);
    setPicked((prev) =>
      prev ? data.basins.find((b) => b.id === prev.id) || data.basins[0] : data.basins[0]
    );
  }

  useEffect(() => {
    refresh().catch((e) => setErr(e.message));
  }, []);

  if (!board) {
    return (
      <div class="yard">
        <TopBar title="江口缫丝坞" subtitle="" view={view} setView={setView} onLogout={onLogout} />
        {err || "装载环盆…"}
      </div>
    );
  }

  const n = board.basins.length;
  async function writeTemp() {
    setErr("");
    try {
      await api(`/api/basins/${picked.id}/readings`, {
        method: "POST",
        body: JSON.stringify({ waterTempC: Number(temp) }),
      });
      await refresh();
    } catch (ex) {
      setErr(ex.message);
    }
  }
  async function setStatus(status) {
    setErr("");
    try {
      const row = await api(`/api/basins/${picked.id}/status`, {
        method: "POST",
        body: JSON.stringify({ status }),
      });
      setPicked(row);
      await refresh();
    } catch (ex) {
      setErr(ex.message);
    }
  }

  return (
    <div class="yard">
      <TopBar
        title={board.filature}
        subtitle={`${board.riverside} · 点盆登记汤温；已缫完须最近汤温 38～42℃；缫丝中改回浸茧须当日合格清汤（余氯 ≥ ${MIN_CHLORINE} 毫克/升）`}
        view={view}
        setView={setView}
        onLogout={onLogout}
      />
      <div class="ring">
        {board.basins.map((b, i) => {
          const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
          const left = 50 + Math.cos(angle) * 38;
          const top = 50 + Math.sin(angle) * 38;
          return (
            <button
              key={b.id}
              class={`basin ${b.status}`}
              style={{ left: `${left}%`, top: `${top}%` }}
              onClick={() => {
                setPicked(b);
                setErr("");
              }}
            >
              <strong>{b.code}</strong>
              <span>{STATUS_LABEL[b.status]}</span>
            </button>
          );
        })}
      </div>
      {picked && (
        <div class="drawer">
          <h3>
            {picked.code} · {STATUS_LABEL[picked.status]}
          </h3>
          <p>最近汤温：{picked.latestTempC ?? "无"} ℃ · 记录 {picked.readingCount} 次</p>
          <p>
            今日清汤余氯：
            {picked.todayChlorineMgL == null
              ? "无记录"
              : `${picked.todayChlorineMgL} 毫克/升${picked.chlorineOk ? "（合格）" : "（不足）"}`}
          </p>
          <input value={temp} onInput={(e) => setTemp(e.target.value)} />
          <button onClick={writeTemp}>登记汤温</button>
          <div>
            <button onClick={() => setStatus("soaking")}>浸茧</button>
            <button onClick={() => setStatus("reeling")}>缫丝中</button>
            <button onClick={() => setStatus("reeled")}>已缫完</button>
          </div>
          {err && <p class="err">{err}</p>}
        </div>
      )}
    </div>
  );
}

function formatTime(iso) {
  if (!iso) return "—";
  return iso.replace("T", " ").slice(0, 16);
}

function ChlorinePage({ user, view, setView, onLogout }) {
  const [records, setRecords] = useState(null);
  const [basins, setBasins] = useState([]);
  const [basinId, setBasinId] = useState("");
  const [value, setValue] = useState("0.3");
  const [err, setErr] = useState("");
  const isAdmin = user.role === "admin";

  async function refresh() {
    const [chlorine, board] = await Promise.all([
      api("/api/chlorine"),
      api("/api/board"),
    ]);
    setRecords(chlorine.records);
    setBasins(board.basins);
    setBasinId((prev) => prev || String(board.basins[0]?.id ?? ""));
  }

  useEffect(() => {
    refresh().catch((e) => setErr(e.message));
  }, []);

  async function submit(e) {
    e.preventDefault();
    setErr("");
    try {
      await api("/api/chlorine", {
        method: "POST",
        body: JSON.stringify({ basinId: Number(basinId), chlorineMgL: Number(value) }),
      });
      await refresh();
    } catch (ex) {
      setErr(ex.message);
    }
  }

  async function voidRecord(id) {
    setErr("");
    try {
      await api(`/api/chlorine/${id}/void`, { method: "POST" });
      await refresh();
    } catch (ex) {
      setErr(ex.message);
    }
  }

  const groups = new Map();
  for (const r of records || []) {
    if (!groups.has(r.sampleDate)) groups.set(r.sampleDate, []);
    groups.get(r.sampleDate).push(r);
  }
  const days = [...groups.keys()].sort().reverse();

  return (
    <div class="chlorine-page">
      <TopBar
        title="清汤余氯"
        subtitle={`按日登记清汤余氯；同一坞每日至多一条未作废记录，余氯 ≥ ${MIN_CHLORINE} 毫克/升方可放行缫丝中改浸茧`}
        view={view}
        setView={setView}
        onLogout={onLogout}
      />
      {isAdmin ? (
        <form class="chlorine-form" onSubmit={submit}>
          <label>
            坞
            <select value={basinId} onInput={(e) => setBasinId(e.target.value)}>
              {basins.map((b) => (
                <option value={b.id} key={b.id}>
                  {b.code}（{STATUS_LABEL[b.status]}）
                </option>
              ))}
            </select>
          </label>
          <label>
            余氯（毫克/升）
            <input value={value} onInput={(e) => setValue(e.target.value)} />
          </label>
          <button type="submit">采样登记</button>
        </form>
      ) : (
        <p class="hint">仅管理员可采样与作废，当前为缫丝工账号。</p>
      )}
      {err && <p class="err">{err}</p>}
      {records === null ? (
        <p>装载清汤记录…</p>
      ) : (
        days.map((day) => (
          <section class="day-block" key={day}>
            <h2>{day}</h2>
            <table class="chlorine-table">
              <thead>
                <tr>
                  <th>坞</th>
                  <th>余氯（毫克/升）</th>
                  <th>采样时刻</th>
                  <th>采样人</th>
                  <th>作废时刻</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {groups.get(day).map((r) => (
                  <tr key={r.id} class={r.voided ? "voided" : ""}>
                    <td>{r.basinCode}</td>
                    <td class={r.voided ? "" : r.qualified ? "ok" : "low"}>
                      {r.chlorineMgL}
                      {!r.voided && (r.qualified ? " · 合格" : " · 不足")}
                    </td>
                    <td>{formatTime(r.takenAt)}</td>
                    <td>{r.sampler}</td>
                    <td>{r.voided ? formatTime(r.voidedAt) : ""}</td>
                    <td>
                      {isAdmin && !r.voided && (
                        <button onClick={() => voidRecord(r.id)}>作废</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        ))
      )}
    </div>
  );
}

function App() {
  const [ready, setReady] = useState(false);
  const [user, setUser] = useState(null);
  const [view, setView] = useState("yard");

  useEffect(() => {
    if (!token()) return;
    api("/api/auth/me")
      .then((u) => {
        setUser(u);
        setReady(true);
      })
      .catch(() => {
        clearToken();
        setReady(false);
      });
  }, []);

  function logout() {
    clearToken();
    setUser(null);
    setReady(false);
  }

  if (!ready || !user) {
    return <Login onOk={(u) => { setUser(u); setReady(true); }} />;
  }
  return view === "chlorine" ? (
    <ChlorinePage user={user} view={view} setView={setView} onLogout={logout} />
  ) : (
    <Yard user={user} view={view} setView={setView} onLogout={logout} />
  );
}

render(<App />, document.getElementById("app"));
