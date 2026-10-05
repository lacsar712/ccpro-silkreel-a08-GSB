import { render } from "preact";
import { useEffect, useState } from "preact/hooks";
import { api, clearToken, setToken, setUser, token, user } from "./api.js";
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
      setUser(data.user);
      onOk();
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

function fmtMoment(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("zh-CN", { hour12: false });
}

function chlorineState(rec) {
  if (!rec) return { text: "今日无清汤余氯记录", ok: false, missing: true };
  if (rec.chlorineMgL < MIN_CHLORINE) {
    return { text: `今日余氯 ${rec.chlorineMgL} 毫克/升，低于 ${MIN_CHLORINE}，不足放行`, ok: false };
  }
  return { text: `今日余氯 ${rec.chlorineMgL} 毫克/升，已达放行线 ${MIN_CHLORINE}`, ok: true };
}

function Yard() {
  const [board, setBoard] = useState(null);
  const [picked, setPicked] = useState(null);
  const [temp, setTemp] = useState("40");
  const [err, setErr] = useState("");

  async function refresh() {
    const data = await api("/api/board");
    setBoard(data);
    setPicked((prev) =>
      prev ? data.basins.find((b) => b.id === prev.id) || data.basins[0] : prev
    );
  }

  useEffect(() => {
    refresh().catch((e) => setErr(e.message));
  }, []);

  if (!board) {
    return <div class="workbench">{err || "装载环盆…"}</div>;
  }

  const n = board.basins.length;
  async function writeTemp() {
    setErr("");
    try {
      const row = await api(`/api/basins/${picked.id}/readings`, {
        method: "POST",
        body: JSON.stringify({ waterTempC: Number(temp) }),
      });
      await refresh();
      setPicked(row);
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
      await refresh();
      setPicked(row);
    } catch (ex) {
      // 缫丝中改回浸茧：当天无合格清汤记录时后端中文挡住。
      setErr(ex.message);
      await refresh();
    }
  }

  const cl = picked ? chlorineState(picked.todayChlorine) : null;
  return (
    <div class="workbench">
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
            清汤余氯：
            {picked.todayChlorine
              ? `${picked.todayChlorine.chlorineMgL} 毫克/升 · 采样人 ${picked.todayChlorine.sampler || "—"}`
              : "今日无记录"}
          </p>
          {picked.status === "reeling" && <p class={cl.ok ? "cl-ok" : "cl-low"}>{cl.text}</p>}
          <input value={temp} onInput={(e) => setTemp(e.target.value)} />
          <button onClick={writeTemp}>登记汤温</button>
          <div>
            <button onClick={() => setStatus("soaking")}>
              {picked.status === "reeling" ? "改回浸茧" : "浸茧"}
            </button>
            <button onClick={() => setStatus("reeling")}>缫丝中</button>
            <button onClick={() => setStatus("reeled")}>已缫完</button>
          </div>
          {picked.status === "reeling" && (
            <p class="hint">缫丝中改回浸茧须当天有未作废且余氯 ≥ {MIN_CHLORINE} 毫克/升的清汤记录。</p>
          )}
          {err && <p class="err">{err}</p>}
        </div>
      )}
    </div>
  );
}

function ChlorinePage() {
  const me = user();
  const isAdmin = me && me.role === "admin";
  const [basins, setBasins] = useState([]);
  const [day, setDay] = useState("");
  const [records, setRecords] = useState([]);
  const [basinId, setBasinId] = useState("");
  const [value, setValue] = useState("0.3");
  const [err, setErr] = useState("");
  const [ok, setOk] = useState("");

  async function loadDay(d) {
    setErr("");
    setOk("");
    const data = await api(`/api/chlorine?day=${encodeURIComponent(d)}`);
    setRecords(data.records);
    setDay(data.day);
  }

  useEffect(() => {
    (async () => {
      try {
        const board = await api("/api/board");
        setBasins(board.basins);
        if (!basinId && board.basins.length) setBasinId(String(board.basins[0].id));
        await loadDay(board.today);
      } catch (e) {
        setErr(e.message);
      }
    })();
  }, []);

  async function pickDay(e) {
    const d = e.target.value;
    if (!d) return;
    try {
      await loadDay(d);
    } catch (ex) {
      setErr(ex.message);
    }
  }

  async function submit(e) {
    e.preventDefault();
    setErr("");
    setOk("");
    try {
      await api("/api/chlorine", {
        method: "POST",
        body: JSON.stringify({ basinId: Number(basinId), chlorineMgL: Number(value) }),
      });
      setOk("清汤余氯已采样登记");
      await loadDay(day);
    } catch (ex) {
      setErr(ex.message);
    }
  }

  async function voidRecord(id) {
    setErr("");
    setOk("");
    try {
      await api(`/api/chlorine/${id}/void`, { method: "POST" });
      setOk("记录已作废");
      await loadDay(day);
    } catch (ex) {
      setErr(ex.message);
    }
  }

  const codeOf = (id) => basins.find((b) => b.id === id)?.code || "";

  return (
    <div class="chlorine">
      <h2>清汤余氯</h2>
      <p class="hint">
        放行线 {MIN_CHLORINE} 毫克/升；同一坞同一自然日至多一条未作废记录。仅管理员可采样、作废。
      </p>
      <div class="day-bar">
        <label>
          日期
          <input type="date" value={day} onInput={pickDay} />
        </label>
      </div>

      {isAdmin && (
        <form class="cl-form" onSubmit={submit}>
          <label>
            坞
            <select value={basinId} onChange={(e) => setBasinId(e.target.value)}>
              {basins.map((b) => (
                <option value={b.id}>
                  {b.code}（{STATUS_LABEL[b.status]}）
                </option>
              ))}
            </select>
          </label>
          <label>
            余氯（毫克/升）
            <input value={value} onInput={(e) => setValue(e.target.value)} inputmode="decimal" />
          </label>
          <button type="submit">采样登记</button>
        </form>
      )}

      {ok && <p class="cl-ok">{ok}</p>}
      {err && <p class="err">{err}</p>}

      <h3>{day} 记录</h3>
      {records.length === 0 ? (
        <p class="hint">当日尚无清汤余氯记录。</p>
      ) : (
        <ul class="cl-list">
          {records.map((r) => {
            const voided = Boolean(r.voidedAt);
            const enough = r.chlorineMgL >= MIN_CHLORINE;
            return (
              <li key={r.id} class={voided ? "cl-row voided" : "cl-row"}>
                <div class="cl-main">
                  <strong>{r.basinCode || codeOf(r.basinId)}</strong>
                  <span class={voided || enough ? "cl-okish" : "cl-low"}>
                    {r.chlorineMgL} 毫克/升{voided ? "" : enough ? "（达标）" : "（不足）"}
                  </span>
                </div>
                <div class="cl-meta">
                  采样 {fmtMoment(r.sampledAt)} · 采样人 {r.sampler || "—"}
                  {voided && <span class="cl-void-tag"> · 已于 {fmtMoment(r.voidedAt)} 作废</span>}
                </div>
                {isAdmin && !voided && (
                  <button class="btn-void" onClick={() => voidRecord(r.id)}>
                    作废
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function Shell() {
  const [view, setView] = useState("yard");
  const me = user();
  function logout() {
    clearToken();
    location.reload();
  }
  return (
    <div class="shell">
      <div class="topbar">
        <div>
          <h1>江口缫丝坞</h1>
          <nav class="tabs">
            <button class={view === "yard" ? "tab active" : "tab"} onClick={() => setView("yard")}>
              环盆作业台
            </button>
            <button class={view === "chlorine" ? "tab active" : "tab"} onClick={() => setView("chlorine")}>
              清汤余氯
            </button>
          </nav>
        </div>
        <div class="who">
          <span class="hint">
            {me?.username}（{me?.role === "admin" ? "管理员" : "缫丝工"}）
          </span>
          <button onClick={logout}>退出</button>
        </div>
      </div>
      {view === "yard" ? <Yard /> : <ChlorinePage />}
    </div>
  );
}

function App() {
  const [ready, setReady] = useState(Boolean(token()));
  return ready ? <Shell /> : <Login onOk={() => setReady(true)} />;
}

render(<App />, document.getElementById("app"));
