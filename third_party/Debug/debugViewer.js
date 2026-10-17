(() => {
  'use strict';

  // 必须与 Debug/DebugSender.py 中的 DEBUG_VIEWER 保持一致
  const UNIQUE_NAME = 'debug_viewer';
  const WS_URL = 'ws://127.0.0.1:5050/ws';

  const el = {
    dot: document.getElementById('dot'),
    statusText: document.getElementById('statusText'),
    agentSelect: document.getElementById('agentSelect'),
    refreshBtn: document.getElementById('refreshBtn'),
    metaText: document.getElementById('metaText'),
    autoScroll: document.getElementById('autoScroll'),
    list: document.getElementById('list'),
    footThread: document.getElementById('footThread'),
    footTime: document.getElementById('footTime'),
    saveDirBtn: document.getElementById('saveDirBtn'),
    saveNowBtn: document.getElementById('saveNowBtn'),
    autoSave: document.getElementById('autoSave'),
    footSave: document.getElementById('footSave'),
  };

  let ws = null;
  let reconnectTimer = null;

  // 存档相关：lastSnapshot 供「保存当前」使用；dirHandle 为空时退化为浏览器下载
  let lastSnapshot = null;
  let dirHandle = null;
  let saveCount = 0;  // 成功落盘数
  let saveSeq = 0;    // 文件名序号，同步自增，保证并发时文件名不撞车
  let lastSavedSignature = null;

  function setConnected(on) {
    el.dot.classList.toggle('on', on);
    el.statusText.textContent = on ? '已连接' : '已断开，重连中…';
  }

  function nearBottom() {
    return el.list.scrollHeight - el.list.scrollTop - el.list.clientHeight < 60;
  }

  function scrollToBottom() {
    el.list.scrollTop = el.list.scrollHeight;
  }

  // ---- 渲染 ---------------------------------------------------------------

  function renderTools(toolCalls) {
    const box = document.createElement('details');
    const sum = document.createElement('summary');
    sum.textContent = `tool_calls (${toolCalls.length})`;
    box.appendChild(sum);
    const pre = document.createElement('pre');
    pre.textContent = toolCalls.map(tc => {
      let args = tc.args;
      try { args = JSON.stringify(tc.args, null, 2); } catch (_) { args = String(tc.args); }
      return `${tc.name}  ${args}`;
    }).join('\n\n');
    box.appendChild(pre);
    return box;
  }

  function renderMessage(m) {
    const row = document.createElement('div');
    row.className = 'msg ' + (m.role || 'system');

    const badge = document.createElement('div');
    badge.className = 'badge';
    badge.textContent = m.role || '?';
    row.appendChild(badge);

    const bubble = document.createElement('div');
    bubble.className = 'bubble';

    if (m.tool_call_id) {
      const tag = document.createElement('div');
      tag.style.cssText = 'font:11px/1.6 var(--mono);color:var(--text-dim);margin-bottom:4px';
      tag.textContent = 'id: ' + m.tool_call_id;
      bubble.appendChild(tag);
    }

    // 思考过程排在正文之上：模型是先想后答
    if (m.thinking) {
      const d = document.createElement('details');
      d.className = 'think';
      const s = document.createElement('summary');
      s.textContent = `thinking · ${m.thinking.length} 字`;
      d.appendChild(s);
      const pre = document.createElement('pre');
      // 同样用 textContent：内容由模型生成，不可当作 HTML 解析
      pre.textContent = m.thinking;
      d.appendChild(pre);
      bubble.appendChild(d);
    }

    const content = document.createElement('div');
    content.className = 'content';
    // 用 textContent 而非 innerHTML：内容由模型生成，不可当作 HTML 解析
    content.textContent = m.content || '';
    bubble.appendChild(content);

    if (Array.isArray(m.tool_calls) && m.tool_calls.length) {
      bubble.appendChild(renderTools(m.tool_calls));
    }
    if (m.usage) {
      const d = document.createElement('details');
      const s = document.createElement('summary');
      s.textContent = 'usage';
      d.appendChild(s);
      const pre = document.createElement('pre');
      try { pre.textContent = JSON.stringify(m.usage, null, 2); }
      catch (_) { pre.textContent = String(m.usage); }
      d.appendChild(pre);
      bubble.appendChild(d);
    }

    row.appendChild(bubble);
    return row;
  }

  // system prompt 由后端从 PromptPiecer 读出来，不属于 state.messages，单独渲染
  function renderSystemPrompt(text) {
    if (!text) return null;
    const box = document.createElement('details');
    box.className = 'sysbox';
    const s = document.createElement('summary');
    s.textContent = `system_prompt · ${text.length} 字`;
    box.appendChild(s);
    const pre = document.createElement('pre');
    // 同样用 textContent：prompt 内容不可当作 HTML 解析
    pre.textContent = text;
    box.appendChild(pre);
    return box;
  }

  function render(snapshot) {
    lastSnapshot = snapshot;
    const keepScroll = el.autoScroll.checked && nearBottom();

    el.list.textContent = '';

    // 即使该会话还没有任何消息，system prompt 也照常显示
    const sysBox = renderSystemPrompt(snapshot.system_prompt);
    if (sysBox) el.list.appendChild(sysBox);

    const msgs = snapshot.messages || [];
    if (!msgs.length) {
      const empty = document.createElement('div');
      empty.className = 'empty';
      empty.textContent = '该会话暂无上下文';
      el.list.appendChild(empty);
    } else {
      const frag = document.createDocumentFragment();
      for (const m of msgs) frag.appendChild(renderMessage(m));
      el.list.appendChild(frag);
    }

    el.metaText.textContent =
      `${msgs.length} 条消息 · ${snapshot.total_tokens || 0} tokens`;

    const extras = snapshot.extras || {};
    const extraKeys = Object.keys(extras);
    if (extraKeys.length) {
      const box = document.createElement('details');
      const s = document.createElement('summary');
      s.textContent = `state 其他字段 (${extraKeys.length}): ${extraKeys.join(', ')}`;
      box.appendChild(s);
      const pre = document.createElement('pre');
      try { pre.textContent = JSON.stringify(extras, null, 2); }
      catch (_) { pre.textContent = String(extras); }
      box.appendChild(pre);
      el.list.appendChild(box);
    }

    el.footThread.textContent = `thread: ${snapshot.thread_id}`;
    const t = new Date((snapshot.timestamp || 0) * 1000);
    el.footTime.textContent = '更新于: ' + t.toLocaleTimeString();

    if (keepScroll) scrollToBottom();
  }

  // ---- 存档：每轮落一个 txt -----------------------------------------------

  function stampOf(ts) {
    const d = new Date((ts || 0) * 1000);
    const p = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
  }

  function safeName(s) {
    return String(s || 'unknown').replace(/[^\w.-]+/g, '_');
  }

  function toolCallsText(toolCalls) {
    return toolCalls.map(tc => {
      let args = tc.args;
      try { args = JSON.stringify(tc.args, null, 2); } catch (_) { args = String(tc.args); }
      return `${tc.name}  ${args}`;
    }).join('\n');
  }

  // 一条消息一行：`角色:正文`，思考过程与工具调用作为缩进行附在后面
  function messageToText(m) {
    const lines = [`${m.role || 'unknown'}:${m.content || ''}`];
    if (m.thinking) lines.push(`  thinking: ${m.thinking}`);
    if (Array.isArray(m.tool_calls) && m.tool_calls.length) {
      lines.push('  tool_calls:');
      for (const l of toolCallsText(m.tool_calls).split('\n')) lines.push('    ' + l);
    }
    if (m.tool_call_id) lines.push(`  tool_call_id: ${m.tool_call_id}`);
    return lines.join('\n');
  }

  // 末条是 ai 说明这一轮已经跑完：它就是本轮输出，剩下的才是喂给模型的输入
  function outputTextOf(m) {
    let out = m.content || '';
    if (Array.isArray(m.tool_calls) && m.tool_calls.length) {
      const calls = toolCallsText(m.tool_calls);
      out = out ? `${out}\n${calls}` : calls;
    }
    return out.trim() || '（空）';
  }

  function buildSaveText(snapshot) {
    const msgs = snapshot.messages || [];
    const last = msgs[msgs.length - 1];
    const finished = !!last && (last.role || '') === 'ai';

    // 最后那条 ai 是本轮输出，不属于「输入上下文」
    const ctxMsgs = finished ? msgs.slice(0, -1) : msgs;
    const output = finished ? outputTextOf(last) : '（本轮尚无模型输出）';

    const parts = [
      `输出：${output}`,
      '',
      '完整输入上下文：',
      `system_prompt:${snapshot.system_prompt || ''}`,
    ];

    if (!ctxMsgs.length) {
      parts.push('（无消息）');
    } else {
      for (const m of ctxMsgs) parts.push(messageToText(m));
    }

    parts.push(
      '',
      '----',
      `agent: ${snapshot.agent_name || ''}`,
      `thread: ${snapshot.thread_id || ''}`,
      `时间: ${stampOf(snapshot.timestamp)}`,
      `消息数: ${msgs.length} · tokens: ${snapshot.total_tokens || 0}`,
      '',
    );

    return parts.join('\n');
  }

  function fileNameOf(snapshot, seq) {
    return `${safeName(snapshot.thread_id || snapshot.agent_name)}_round${String(seq).padStart(3, '0')}_${stampOf(snapshot.timestamp)}.txt`;
  }

  function setSaveStatus(text) {
    el.footSave.textContent = `保存: ${text}`;
  }

  // File System Access API：选一次目录后即可静默写盘，Chrome/Edge 支持
  async function pickDir() {
    if (!window.showDirectoryPicker) {
      setSaveStatus('浏览器不支持目录写入，将改用下载');
      return null;
    }
    try {
      dirHandle = await window.showDirectoryPicker();
      setSaveStatus(`${dirHandle.name} · 待保存`);
      return dirHandle;
    } catch (_) {
      return null; // 用户取消
    }
  }

  async function ensureDirPermission() {
    if (!dirHandle || !dirHandle.queryPermission) return !!dirHandle;
    const opts = { mode: 'readwrite' };
    if ((await dirHandle.queryPermission(opts)) === 'granted') return true;
    return (await dirHandle.requestPermission(opts)) === 'granted';
  }

  function downloadText(name, text) {
    const url = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function writeText(name, text) {
    if (!dirHandle) {
      downloadText(name, text);
      return '已下载（未选目录）';
    }
    if (!(await ensureDirPermission())) {
      downloadText(name, text);
      return '目录无权限，已改下载';
    }
    const fh = await dirHandle.getFileHandle(name, { create: true });
    const w = await fh.createWritable();
    await w.write(text);
    await w.close();
    return dirHandle.name || '已选目录';
  }

  async function saveSnapshot(snapshot, seq) {
    const name = fileNameOf(snapshot, seq);
    try {
      const where = await writeText(name, buildSaveText(snapshot));
      saveCount += 1;
      setSaveStatus(`${where} · 已存 ${saveCount} 个 · 最近 ${name}`);
    } catch (e) {
      setSaveStatus(`失败 ${name}: ${e && e.message ? e.message : e}`);
    }
  }

  // 有目录就静默落盘；没目录只在用户手动触发时才走下载，避免自动保存刷屏
  function saveCurrent(snapshot, { force = false } = {}) {
    if (!snapshot) return;
    // 同一轮可能被重复推送（手动刷新/切换 agent），用 signature 去重，避免刷出一堆重复文件
    if (!force && snapshot.signature && snapshot.signature === lastSavedSignature) return;
    lastSavedSignature = snapshot.signature || null;
    saveSnapshot(snapshot, ++saveSeq);
  }

  // ---- 连接 ---------------------------------------------------------------

  function requestContext() {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        action: 'request_context',
        agent_name: el.agentSelect.value,
      }));
    }
  }

  function connect() {
    ws = new WebSocket(WS_URL);

    ws.onopen = () => {
      setConnected(true);
      // 第一条消息用于向 MCPServer 注册身份
      ws.send(JSON.stringify({ unique_name: UNIQUE_NAME }));
      ws.send(JSON.stringify({ action: 'list_agents' }));
      requestContext();
    };

    ws.onmessage = (ev) => {
      let data;
      try { data = JSON.parse(ev.data); } catch (_) { return; }

      if (data.action === 'context') {
        render(data.snapshot);
        if (el.autoSave.checked) saveCurrent(data.snapshot);
      } else if (data.action === 'agent_list') {
        const agents = data.agents || [];
        if (agents.length) {
          const cur = el.agentSelect.value;
          el.agentSelect.textContent = '';
          for (const a of agents) {
            const opt = document.createElement('option');
            opt.value = a;
            opt.textContent = a;
            el.agentSelect.appendChild(opt);
          }
          el.agentSelect.value = agents.includes(cur) ? cur : 'momo';
        }
      }
    };

    ws.onclose = () => {
      setConnected(false);
      clearTimeout(reconnectTimer);
      reconnectTimer = setTimeout(connect, 2000);
    };

    ws.onerror = () => { try { ws.close(); } catch (_) {} };
  }

  el.refreshBtn.addEventListener('click', requestContext);
  el.agentSelect.addEventListener('change', requestContext);
  el.list.addEventListener('scroll', () => {}, { passive: true });

  el.saveDirBtn.addEventListener('click', () => { pickDir(); });
  el.saveNowBtn.addEventListener('click', () => { saveCurrent(lastSnapshot, { force: true }); });

  el.autoSave.addEventListener('change', async () => {
    if (!el.autoSave.checked) return;
    // 勾选即视为用户手势，此刻可以弹目录选择器
    if (!dirHandle) {
      const h = await pickDir();
      if (!h) {
        el.autoSave.checked = false;
        return;
      }
    }
    // 立即补存当前这一帧，便于和之前的轮次对上
    saveCurrent(lastSnapshot, { force: true });
  });

  connect();
})();
