<script>
  let session = null;
  let view = "logs"; // logs=总表，comp=温度补偿专页
  let logs = [];
  let ledger = [];
  let loginUser = "surveyor";
  let loginPass = "surv123456";
  let error = "";
  let loading = false;
  let timer;

  // 补偿专页表单：系数、洞温两块的状态由报送块一起带走（原子提交）
  let coeffK = "0.05";
  let baselineTemp = "";
  let measuredTemp = "";
  let chainage = "";
  let deltaMm = "";
  let compError = "";
  let compOk = "";

  // 在线展示改数
  let editId = null;
  let editValue = "";
  let editNote = "";

  $: isWriter = session?.role === "writer";
  $: tempGap =
    baselineTemp !== "" && measuredTemp !== "" && !isNaN(Number(baselineTemp)) && !isNaN(Number(measuredTemp))
      ? Number(measuredTemp) - Number(baselineTemp)
      : null;
  $: previewDrift =
    tempGap !== null && coeffK !== "" && !isNaN(Number(coeffK))
      ? Math.round(Number(coeffK) * tempGap * 1000) / 1000
      : null;

  function headers() {
    return session ? { Authorization: "Bearer " + session.token } : {};
  }

  async function refresh() {
    if (!session) return;
    const [r1, r2] = await Promise.all([
      fetch("/api/logs", { headers: headers() }),
      fetch("/api/ledger", { headers: headers() }),
    ]);
    if (r1.status === 401 || r2.status === 401) {
      logout();
      return;
    }
    if (r1.ok) logs = await r1.json();
    if (r2.ok) ledger = await r2.json();
  }

  async function login() {
    error = "";
    loading = true;
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: loginUser, password: loginPass }),
      });
      const data = await res.json();
      if (!res.ok) {
        error = data.detail || "登录失败";
        return;
      }
      session = { token: data.access_token, username: data.username, role: data.role };
      localStorage.setItem("tunnel_session", JSON.stringify(session));
      await refresh();
      timer = setInterval(refresh, 2000);
    } catch {
      error = "无法连接接口";
    } finally {
      loading = false;
    }
  }

  function logout() {
    if (timer) clearInterval(timer);
    session = null;
    logs = [];
    ledger = [];
    localStorage.removeItem("tunnel_session");
  }

  async function submitReport() {
    compError = "";
    compOk = "";
    loading = true;
    // 空串发 null，绝不能 Number("")→0 把“没填洞温”蒙成 0℃；缺料由后端退回
    const numOrNull = (s) => (s === "" || s === null || s === undefined ? null : Number(s));
    try {
      const res = await fetch("/api/logs", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers() },
        body: JSON.stringify({
          chainage,
          delta_mm: numOrNull(deltaMm),
          coeff_k: numOrNull(coeffK),
          baseline_temp_c: numOrNull(baselineTemp),
          measured_temp_c: numOrNull(measuredTemp),
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        // 缺洞温、系数越界等：后端退回并给人话
        compError = data.detail || "提交被退回";
        return;
      }
      compOk = `已进队（编号 ${data.id}）：进队记录与补偿账一起落账，等后台扣漂出结论`;
      chainage = "";
      deltaMm = "";
      // 系数与基准洞温是该断面的常数，保留；当时洞温每测不同，清掉
      measuredTemp = "";
      await refresh();
    } catch {
      compError = "提交时网络异常";
    } finally {
      loading = false;
    }
  }

  function startEdit(row) {
    editId = row.id;
    editValue = String(row.online_mm ?? "");
    editNote = "";
  }

  async function saveDisplay(row) {
    compError = "";
    try {
      const res = await fetch(`/api/logs/${row.id}/display`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...headers() },
        body: JSON.stringify({ online_mm: editValue === "" ? null : Number(editValue), note: editNote }),
      });
      const data = await res.json();
      if (!res.ok) {
        error = data.detail || "改展示失败";
        return;
      }
      editId = null;
      await refresh();
    } catch {
      error = "改展示时网络异常";
    }
  }

  function fmt(v, digits = 2) {
    return v === null || v === undefined ? "—" : Number(v).toFixed(digits);
  }

  function fmtTime(iso) {
    if (!iso) return "—";
    return iso.replace("T", " ").slice(0, 19);
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
  header.top {
    display: flex; align-items: center; gap: 1rem; flex-wrap: wrap;
    border-bottom: 2px solid #d97706; padding-bottom: 0.75rem; margin-bottom: 1.25rem;
  }
  h1 { color: #fbbf24; margin: 0; font-size: 1.35rem; }
  nav { display: flex; gap: 0.5rem; }
  nav button {
    background: #44403c; color: #d6d3d1; padding: 0.4rem 0.9rem; font-weight: 500;
  }
  nav button.active { background: #d97706; color: #fff; font-weight: 700; }
  .spacer { flex: 1; }
  .who { color: #a8a29e; font-size: 0.85rem; }
  .sub { color: #a8a29e; margin-bottom: 1.25rem; }
  section {
    background: #292524; border: 1px solid #44403c; border-radius: 8px;
    padding: 1rem 1.25rem; margin-bottom: 1rem;
  }
  section > h2 { margin: 0 0 0.6rem; font-size: 1rem; color: #fbbf24; }
  .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 0 1.25rem; }
  @media (max-width: 720px) { .grid2 { grid-template-columns: 1fr; } }
  label { display: block; font-size: 0.85rem; color: #d6d3d1; margin-bottom: 0.25rem; }
  input {
    width: 100%; box-sizing: border-box; padding: 0.5rem 0.65rem; border-radius: 6px;
    border: 1px solid #57534e; background: #0c0a09; color: #fafaf9; margin-bottom: 0.75rem;
  }
  button {
    cursor: pointer; padding: 0.5rem 1rem; border: none; border-radius: 6px;
    background: #d97706; color: #fff; font-weight: 600;
  }
  button.secondary { background: #57534e; }
  button.mini { padding: 0.2rem 0.55rem; font-size: 0.78rem; }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
  .err { color: #fb7185; }
  .ok-msg { color: #86efac; }
  .hint { color: #a8a29e; font-size: 0.8rem; margin: 0 0 0.6rem; }
  table { width: 100%; border-collapse: collapse; font-size: 0.86rem; }
  th, td { text-align: left; padding: 0.45rem; border-bottom: 1px solid #44403c; white-space: nowrap; }
  th { color: #d6d3d1; font-weight: 600; }
  .tag { padding: 0.1rem 0.4rem; border-radius: 4px; font-size: 0.8rem; }
  .ok { background: #14532d; color: #86efac; }
  .bad { background: #7f1d1d; color: #fca5a5; }
  .pending { background: #713f12; color: #fde68a; }
  details { margin-top: 0.4rem; }
  details summary { cursor: pointer; color: #a8a29e; font-size: 0.78rem; }
  .rev { font-size: 0.78rem; color: #d6d3d1; padding: 0.15rem 0; }
  .locked { color: #fde68a; font-size: 0.85rem; }
</style>

<main>
  <h1 style="margin:0 0 0.25rem">隧道收敛测缝台</h1>
  {#if !session}
    <p class="sub">二衬龄期内洞温会把测缝读数拧偏，下结论前先扣漂移。登录框已预填可写账号 surveyor / surv123456；巡检员 inspector / insp123456 只读。</p>
    <section>
      <label>用户名</label>
      <input bind:value={loginUser} autocomplete="off" />
      <label>密码</label>
      <input type="password" bind:value={loginPass} autocomplete="off" />
      <button disabled={loading} on:click={login}>登录</button>
      {#if error}<p class="err">{error}</p>{/if}
    </section>
  {:else}
    <header class="top">
      <h1>隧道收敛测缝台</h1>
      <nav>
        <button class={view === "logs" ? "active" : ""} on:click={() => (view = "logs")}>总表</button>
        <button class={view === "comp" ? "active" : ""} on:click={() => (view = "comp")}>温度补偿专页</button>
      </nav>
      <span class="spacer"></span>
      <span class="who">{session.username}（{isWriter ? "测量员·可提交" : "巡检员·只读"}）</span>
      <button class="secondary mini" on:click={logout}>退出</button>
    </header>
    {#if error}<p class="err">{error}</p>{/if}

    {#if view === "logs"}
      <p class="sub">总表只放进队读数与结论：原始值、扣漂后值、在线展示值分列。系数不进总表，要查去温度补偿专页的流水块。</p>
      <section>
        <table>
          <thead>
            <tr>
              <th>编号</th><th>桩号</th><th>原始mm</th><th>扣漂后mm</th><th>漂移mm</th>
              <th>洞温℃</th><th>在线展示mm</th><th>状态</th><th>结论</th><th>说明</th>
            </tr>
          </thead>
          <tbody>
            {#each logs as row}
              <tr>
                <td>{row.id}</td>
                <td>{row.chainage}</td>
                <td>{fmt(row.delta_mm)}</td>
                <td><strong>{fmt(row.corrected_mm)}</strong></td>
                <td>{fmt(row.drift_mm)}</td>
                <td>{fmt(row.temp_now_c, 1)}</td>
                <td>
                  {fmt(row.online_mm)}
                  {#if isWriter && row.status === "done"}
                    {#if editId === row.id}
                      <span style="white-space:nowrap">
                        <input style="width:5.5rem;display:inline-block;margin:0 0.3rem" type="number" step="0.1" bind:value={editValue} />
                        <input style="width:9rem;display:inline-block;margin:0 0.3rem" placeholder="改数原因（留痕）" bind:value={editNote} />
                        <button class="mini" on:click={() => saveDisplay(row)}>存</button>
                        <button class="secondary mini" on:click={() => (editId = null)}>取消</button>
                      </span>
                    {:else}
                      <button class="secondary mini" on:click={() => startEdit(row)}>改展示</button>
                    {/if}
                  {/if}
                  {#if row.revisions?.length}
                    <details>
                      <summary>改数留痕 {row.revisions.length} 次（账内旧值可翻）</summary>
                      {#each row.revisions as rev}
                        <div class="rev">
                          {fmtTime(rev.edited_at)} {rev.edited_by}：{fmt(rev.old_mm)} → {fmt(rev.new_mm)}
                          {rev.note ? "（" + rev.note + "）" : ""}
                        </div>
                      {/each}
                    </details>
                  {/if}
                </td>
                <td><span class="tag {row.status === "pending" ? "pending" : "ok"}">{row.status === "pending" ? "待扣漂" : "已完成"}</span></td>
                <td>
                  {#if row.verdict}
                    <span class="tag {row.verdict === "合格" ? "ok" : "bad"}">{row.verdict}</span>
                  {:else}—{/if}
                </td>
                <td style="white-space:normal">{row.reason ?? "—"}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </section>
    {:else}
      <p class="sub">
        温度补偿专页四块：<strong>系数</strong>（测量员写温度系数）、<strong>洞温</strong>（基准洞温与当时洞温）、
        <strong>流水</strong>（补偿账，只可翻不可改）、<strong>报送</strong>（四块材料同单原子提交，拆两边不齐整单作废）。
      </p>
      {#if !isWriter}
        <p class="locked">巡检员只读：能翻流水、翻总表；系数、洞温、报送、改展示均不可操作。</p>
      {/if}

      <div class="grid2">
        <!-- 块一：系数（不进总表格子） -->
        <section>
          <h2>① 温度系数（mm/℃）</h2>
          <p class="hint">只接受大于 0 且不超过 0.20 mm/℃ 的系数；常用 0.05，即洞温每抬高 20℃ 约扣 1 mm 漂移。</p>
          <label>温度系数 k</label>
          <input type="number" step="0.001" min="0.001" max="0.20" bind:value={coeffK} disabled={!isWriter} />
        </section>

        <!-- 块二：洞温 -->
        <section>
          <h2>② 洞温（℃）</h2>
          <p class="hint">
            基准洞温与当时洞温都要在 -20～60℃ 之间。当前温差
            <strong>{tempGap === null ? "—" : tempGap.toFixed(1)}℃</strong>
            ，预计漂移 <strong>{previewDrift === null ? "—" : previewDrift.toFixed(3)} mm</strong>
            （后台以提交时快照为准）。
          </p>
          <label>基准洞温</label>
          <input type="number" step="0.1" bind:value={baselineTemp} disabled={!isWriter} />
          <label>当时洞温</label>
          <input type="number" step="0.1" bind:value={measuredTemp} disabled={!isWriter} />
        </section>
      </div>

      <!-- 块三：流水（补偿账） -->
      <section>
        <h2>③ 补偿账流水（原始值与扣漂后值都进账，只可翻不可改）</h2>
        <div style="overflow-x:auto">
          <table>
            <thead>
              <tr>
                <th>账号</th><th>桩号</th><th>系数</th><th>基准℃</th><th>当时℃</th>
                <th>原始mm</th><th>漂移mm</th><th>扣漂后mm</th><th>结论</th><th>填报人</th><th>时间</th>
              </tr>
            </thead>
            <tbody>
              {#each ledger as row}
                <tr>
                  <td>{row.id}</td>
                  <td>{row.chainage}</td>
                  <td>{fmt(row.coeff_k, 3)}</td>
                  <td>{fmt(row.baseline_temp_c, 1)}</td>
                  <td>{fmt(row.measured_temp_c, 1)}</td>
                  <td>{fmt(row.raw_mm)}</td>
                  <td>{fmt(row.drift_mm)}</td>
                  <td><strong>{fmt(row.corrected_mm)}</strong></td>
                  <td>
                    {#if row.verdict}
                      <span class="tag {row.verdict === "合格" ? "ok" : "bad"}">{row.verdict}</span>
                    {:else}
                      <span class="tag pending">待扣漂</span>
                    {/if}
                  </td>
                  <td>{row.created_by}</td>
                  <td>{fmtTime(row.created_at)}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </section>

      <!-- 块四：报送 -->
      {#if isWriter}
        <section>
          <h2>④ 报送（进队记录与补偿账一起提交）</h2>
          <p class="hint">系数取①块、两个洞温取②块；缺洞温或系数越界会被退回。后台用当时洞温扣漂后，按 ±3.0 mm 判合格或超限。</p>
          <div class="grid2">
            <div>
              <label>里程桩号</label>
              <input placeholder="例如 K20+050" bind:value={chainage} />
            </div>
            <div>
              <label>测缝原始读数（毫米，可正可负）</label>
              <input type="number" step="0.01" bind:value={deltaMm} />
            </div>
          </div>
          <button disabled={loading} on:click={submitReport}>提交（记录与补偿账同单）</button>
          {#if compError}<p class="err">{compError}</p>{/if}
          {#if compOk}<p class="ok-msg">{compOk}</p>{/if}
        </section>
      {/if}
    {/if}
  {/if}
</main>
