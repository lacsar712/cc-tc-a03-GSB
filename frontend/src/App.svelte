<script>
  let session = null;
  let view = "main"; // main=总表, comp=补偿专页
  let logs = [];
  let settings = null;
  let temps = [];
  let ledger = [];

  let loginUser = "surveyor";
  let loginPass = "surv123456";
  let loginError = "";

  // 报送表单
  let chainage = "";
  let deltaMm = "";
  let submitError = "";

  // 系数设置表单
  let coefInput = "";
  let baseTempInput = "";
  let coefError = "";
  let coefNote = "";
  let settingsPrefilled = false;

  // 洞温登记表单
  let tempInput = "";
  let tempError = "";

  // 总表改数
  let editId = null;
  let editChainage = "";
  let editDelta = "";
  let editError = "";

  let loading = false;
  let timer;

  $: isWriter = session?.role === "writer";
  $: latestTemp = temps.length > 0 ? temps[0] : null;
  $: if (settings && !settingsPrefilled) {
    coefInput = String(settings.coefficient);
    baseTempInput = String(settings.baseline_temp_c);
    settingsPrefilled = true;
  }

  function headers() {
    return session ? { Authorization: "Bearer " + session.token } : {};
  }

  async function req(path, method = "GET", body = null) {
    const opts = { method, headers: { ...headers() } };
    if (body !== null) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    let res;
    try {
      res = await fetch(path, opts);
    } catch {
      return { ok: false, status: 0, data: { detail: "无法连接接口" } };
    }
    if (res.status === 401) {
      logout();
      return { ok: false, status: 401, data: {} };
    }
    const data = await res.json().catch(() => ({}));
    return { ok: res.ok, status: res.status, data };
  }

  async function refresh() {
    if (!session) return;
    const r = await req("/api/logs");
    if (r.status === 401) return;
    if (r.ok) logs = r.data;
    const s = await req("/api/compensation/settings");
    if (s.ok) settings = s.data;
    const t = await req("/api/compensation/temps");
    if (t.ok) temps = t.data;
    const l = await req("/api/compensation/ledger");
    if (l.ok) ledger = l.data;
  }

  function go(v) {
    view = v;
    refresh();
  }

  async function login() {
    loginError = "";
    loading = true;
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: loginUser, password: loginPass }),
      });
      const data = await res.json();
      if (!res.ok) {
        loginError = data.detail || "登录失败";
        return;
      }
      session = { token: data.access_token, username: data.username, role: data.role };
      localStorage.setItem("tunnel_session", JSON.stringify(session));
      await refresh();
      timer = setInterval(refresh, 2000);
    } catch {
      loginError = "无法连接接口";
    } finally {
      loading = false;
    }
  }

  function logout() {
    if (timer) clearInterval(timer);
    session = null;
    logs = [];
    settings = null;
    temps = [];
    ledger = [];
    editId = null;
    settingsPrefilled = false;
    coefInput = "";
    baseTempInput = "";
    localStorage.removeItem("tunnel_session");
  }

  async function submit() {
    submitError = "";
    loading = true;
    try {
      const r = await req("/api/logs", "POST", {
        chainage,
        delta_mm: Number(deltaMm),
      });
      if (!r.ok) {
        submitError = r.data.detail || "提交失败";
        return;
      }
      chainage = "";
      deltaMm = "";
      await refresh();
    } finally {
      loading = false;
    }
  }

  async function saveSettings() {
    coefError = "";
    coefNote = "";
    loading = true;
    try {
      const r = await req("/api/compensation/settings", "PUT", {
        coefficient: Number(coefInput),
        baseline_temp_c: Number(baseTempInput),
      });
      if (!r.ok) {
        coefError = r.data.detail || "保存失败";
        return;
      }
      coefNote = "系数和基准洞温已保存";
      await refresh();
    } finally {
      loading = false;
    }
  }

  async function addTemp() {
    tempError = "";
    loading = true;
    try {
      const r = await req("/api/compensation/temps", "POST", {
        temp_c: Number(tempInput),
      });
      if (!r.ok) {
        tempError = r.data.detail || "登记失败";
        return;
      }
      tempInput = "";
      await refresh();
    } finally {
      loading = false;
    }
  }

  function startEdit(row) {
    editId = row.id;
    editChainage = row.chainage;
    editDelta = row.delta_mm;
    editError = "";
  }

  async function saveEdit() {
    editError = "";
    loading = true;
    try {
      const r = await req(`/api/logs/${editId}`, "PATCH", {
        chainage: editChainage,
        delta_mm: Number(editDelta),
      });
      if (!r.ok) {
        editError = r.data.detail || "保存失败";
        return;
      }
      editId = null;
      await refresh();
    } finally {
      loading = false;
    }
  }

  function fmtTime(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    return isNaN(d) ? iso : d.toLocaleString();
  }

  const raw = localStorage.getItem("tunnel_session");
  if (raw) {
    try {
      session = JSON.parse(raw);
      refresh();
      timer = setInterval(refresh, 2000);
    } catch {
      localStorage.removeItem("tunnel_session");
    }
  }
</script>

<style>
  :global(body) {
    margin: 0;
    font-family: "Segoe UI", system-ui, sans-serif;
    background: #1c1917;
    color: #f5f5f4;
  }
  main { max-width: 1080px; margin: 0 auto; padding: 1.5rem; }
  h1 { color: #fbbf24; margin: 0; font-size: 1.3rem; }
  h2 { color: #fbbf24; font-size: 1.05rem; margin: 0 0 0.6rem; }
  .topbar {
    display: flex; align-items: center; gap: 1.25rem; flex-wrap: wrap;
    background: #292524; border-bottom: 1px solid #44403c;
    padding: 0.7rem 1.5rem;
  }
  .topbar nav { display: flex; gap: 0.5rem; }
  .topbar .who { margin-left: auto; display: flex; align-items: center; gap: 0.6rem; color: #d6d3d1; font-size: 0.9rem; }
  .navbtn {
    background: transparent; color: #d6d3d1; border: 1px solid #57534e;
    padding: 0.35rem 0.9rem; border-radius: 6px; font-weight: 600;
  }
  .navbtn.active { background: #d97706; border-color: #d97706; color: #fff; }
  .sub { color: #a8a29e; margin-bottom: 1.25rem; }
  section {
    background: #292524; border: 1px solid #44403c; border-radius: 8px;
    padding: 1rem 1.25rem; margin-bottom: 1rem;
  }
  label { display: block; font-size: 0.85rem; color: #d6d3d1; margin-bottom: 0.25rem; }
  input {
    width: 100%; box-sizing: border-box; padding: 0.5rem 0.65rem; border-radius: 6px;
    border: 1px solid #57534e; background: #0c0a09; color: #fafaf9; margin-bottom: 0.75rem;
  }
  input.cell { margin-bottom: 0; padding: 0.3rem 0.5rem; }
  button {
    cursor: pointer; padding: 0.5rem 1rem; border: none; border-radius: 6px;
    background: #d97706; color: #fff; font-weight: 600;
  }
  button.secondary { background: #57534e; }
  .err { color: #fb7185; }
  .oknote { color: #86efac; }
  .hint { color: #a8a29e; font-size: 0.85rem; }
  table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
  th, td { text-align: left; padding: 0.45rem; border-bottom: 1px solid #44403c; }
  .tag { padding: 0.1rem 0.4rem; border-radius: 4px; font-size: 0.8rem; }
  .ok { background: #14532d; color: #86efac; }
  .bad { background: #7f1d1d; color: #fca5a5; }
  .pending { background: #713f12; color: #fde68a; }
  .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; }
  .rowflex { display: flex; gap: 0.6rem; align-items: flex-start; }
  .rowflex input { max-width: 220px; }
  .nowrap { white-space: nowrap; }
</style>

{#if !session}
  <main>
    <h1>隧道收敛测缝台</h1>
    <p class="sub">二衬龄期内洞温会拧偏测缝读数，后台下结论前先按系数扣漂。登录框已预填可写账号 surveyor / surv123456。</p>
    <section>
      <label>用户名</label>
      <input bind:value={loginUser} autocomplete="off" />
      <label>密码</label>
      <input type="password" bind:value={loginPass} autocomplete="off" />
      <button disabled={loading} on:click={login}>登录</button>
      {#if loginError}<p class="err">{loginError}</p>{/if}
    </section>
  </main>
{:else}
  <header class="topbar">
    <h1>隧道收敛测缝台</h1>
    <nav>
      <button class="navbtn" class:active={view === "main"} on:click={() => go("main")}>总表</button>
      <button class="navbtn" class:active={view === "comp"} on:click={() => go("comp")}>补偿专页</button>
    </nav>
    <div class="who">
      <span>{session.username}（{isWriter ? "测量员·可写" : "巡检员·只读"}）</span>
      <button class="secondary" disabled={loading} on:click={refresh}>刷新</button>
      <button class="secondary" on:click={logout}>退出</button>
    </div>
  </header>
  <main>
    {#if view === "main"}
      <section>
        <h2>收敛总表</h2>
        <table>
          <thead>
            <tr><th>编号</th><th>桩号</th><th>收敛mm</th><th>状态</th><th>结论</th><th>说明</th>{#if isWriter}<th>操作</th>{/if}</tr>
          </thead>
          <tbody>
            {#each logs as row}
              <tr>
                <td>{row.id}</td>
                {#if editId === row.id}
                  <td><input class="cell" bind:value={editChainage} /></td>
                  <td><input class="cell" type="number" step="0.1" bind:value={editDelta} /></td>
                {:else}
                  <td>{row.chainage}</td>
                  <td>{row.delta_mm}</td>
                {/if}
                <td><span class="tag {row.status === 'pending' ? 'pending' : 'ok'}">{row.status === 'pending' ? '待处理' : '已完成'}</span></td>
                <td>
                  {#if row.verdict}
                    <span class="tag {row.verdict === '合格' ? 'ok' : 'bad'}">{row.verdict}</span>
                  {:else}—{/if}
                </td>
                <td>{row.reason ?? "—"}</td>
                {#if isWriter}
                  <td class="nowrap">
                    {#if editId === row.id}
                      <button disabled={loading} on:click={saveEdit}>保存</button>
                      <button class="secondary" on:click={() => (editId = null)}>取消</button>
                    {:else}
                      <button class="secondary" on:click={() => startEdit(row)}>改数</button>
                    {/if}
                  </td>
                {/if}
              </tr>
            {/each}
          </tbody>
        </table>
        {#if editError}<p class="err">{editError}</p>{/if}
        <p class="hint">结论按扣漂后毫米判定（±3.0 mm）。改数只动在线展示；提交那一刻落进补偿台账的原始值、洞温、系数和扣漂后毫米不会跟着变，去「补偿专页」可翻旧账。</p>
      </section>
    {:else}
      <section>
        <h2>① 系数设置</h2>
        <p class="hint">扣漂公式：扣漂后毫米 = 原始值 − 系数 ×（当时洞温 − 基准洞温）。系数允许 0.001~0.5 mm/℃，基准洞温允许 -20~60 ℃。</p>
        {#if isWriter}
          <div class="grid2">
            <div>
              <label>补偿系数（mm/℃）</label>
              <input type="number" step="0.001" bind:value={coefInput} />
            </div>
            <div>
              <label>基准洞温（℃）</label>
              <input type="number" step="0.1" bind:value={baseTempInput} />
            </div>
          </div>
          <button disabled={loading} on:click={saveSettings}>保存系数</button>
          {#if coefError}<p class="err">{coefError}</p>{/if}
          {#if coefNote}<p class="oknote">{coefNote}</p>{/if}
        {:else}
          <p>当前系数：{settings ? settings.coefficient + " mm/℃" : "未设置"}；基准洞温：{settings ? settings.baseline_temp_c + " ℃" : "未设置"}</p>
          <p class="hint">巡检员只读，不能改系数。</p>
        {/if}
      </section>

      <section>
        <h2>② 洞温流水</h2>
        {#if isWriter}
          <div class="rowflex">
            <input type="number" step="0.1" placeholder="当前洞温 ℃" bind:value={tempInput} />
            <button disabled={loading} on:click={addTemp}>登记洞温</button>
          </div>
          {#if tempError}<p class="err">{tempError}</p>{/if}
        {/if}
        <table>
          <thead><tr><th>编号</th><th>洞温℃</th><th>登记人</th><th>登记时间</th></tr></thead>
          <tbody>
            {#each temps as t}
              <tr><td>{t.id}</td><td>{t.temp_c}</td><td>{t.created_by}</td><td>{fmtTime(t.created_at)}</td></tr>
            {/each}
          </tbody>
        </table>
        {#if temps.length === 0}<p class="hint">还没有洞温记录，提交测量前要先登记。</p>{/if}
      </section>

      <section>
        <h2>③ 补偿台账</h2>
        <p class="hint">提交那一刻落账：原始值和扣漂后值都在这儿。事后有人在总表改展示数字，这里当时记下的旧值不变，随时可翻。</p>
        <table>
          <thead>
            <tr><th>编号</th><th>桩号</th><th>原始mm</th><th>当时洞温℃</th><th>系数</th><th>基准℃</th><th>漂移mm</th><th>扣漂后mm</th><th>结论</th><th>落账时间</th></tr>
          </thead>
          <tbody>
            {#each ledger as e}
              <tr>
                <td>{e.log_id}</td>
                <td>{e.chainage}</td>
                <td>{e.raw_mm}</td>
                <td>{e.temp_c}</td>
                <td>{e.coefficient}</td>
                <td>{e.baseline_temp_c}</td>
                <td>{e.drift_mm}</td>
                <td>{e.compensated_mm}</td>
                <td>
                  {#if e.verdict}
                    <span class="tag {e.verdict === '合格' ? 'ok' : 'bad'}">{e.verdict}</span>
                  {:else}—{/if}
                </td>
                <td>{fmtTime(e.created_at)}</td>
              </tr>
            {/each}
          </tbody>
        </table>
        {#if ledger.length === 0}<p class="hint">还没有补偿账记录。</p>{/if}
      </section>

      <section>
        <h2>④ 报送</h2>
        {#if isWriter}
          <p class="hint">
            将按 系数 {settings ? settings.coefficient : "未设置"} mm/℃、基准 {settings ? settings.baseline_temp_c : "未设置"} ℃、最新洞温 {latestTemp ? latestTemp.temp_c + " ℃" : "未登记"} 扣漂；
            进队记录和补偿账一起落库，后台线程认领后按扣漂后毫米出合格或超限。
          </p>
          <label>里程桩号</label>
          <input placeholder="例如 K20+050" bind:value={chainage} />
          <label>原始收敛（毫米，可正可负）</label>
          <input type="number" step="0.1" bind:value={deltaMm} />
          <button disabled={loading} on:click={submit}>提交（进队并落补偿账）</button>
          {#if submitError}<p class="err">{submitError}</p>{/if}
        {:else}
          <p class="hint">巡检员只读，只能翻表翻账，不能报送。</p>
        {/if}
      </section>
    {/if}
  </main>
{/if}
