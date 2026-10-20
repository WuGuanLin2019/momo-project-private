// ---------- 调试浮层 ----------
// 无 DevTools，console 同步到画面浮层
// (function () {
//     const dbg = document.getElementById("debug");
//     const MAX_LINES = 30;
//     function _fmt(a) {
//         if (typeof a === "object") {
//             try { return JSON.stringify(a); } catch (e) { return String(a); }
//         }
//         return String(a);
//     }
//     function _push(text) {
//         if (!dbg) return;
//         const line = document.createElement("div");
//         line.textContent = text;
//         // 新的插顶部，旧的淘汰
//         dbg.insertBefore(line, dbg.firstChild);
//         while (dbg.childNodes.length > MAX_LINES) {
//             dbg.removeChild(dbg.lastChild);
//         }
//     }
//     ["log", "info", "warn", "error"].forEach(function (level) {
//         const orig = console[level] ? console[level].bind(console) : function () {};
//         console[level] = function () {
//             const args = Array.prototype.slice.call(arguments);
//             try { _push(args.map(_fmt).join(" ")); } catch (e) {}
//             orig.apply(null, args);
//         };
//     });
// })();

// ---------- 字幕：按时间渲染，抗节流 ----------
// 后台节流下按 elapsed 算索引，不丢字

const subtitleEl =
    typeof subtitle !== "undefined" && subtitle
        ? subtitle
        : document.getElementById("subtitle");

let _rafId = null;        // 可见时用 rAF
let _fallbackTimer = null;// rAF 停摆时定时器兜底
let _task = null;         // { base, text, intervalMs, startTime, clearAt }

function _now() {
    return typeof performance !== "undefined" && performance.now
        ? performance.now()
        : Date.now();
}

// 按已过时间算显示到第几字
function _render() {
    if (!_task) return true;

    const elapsed = _now() - _task.startTime;
    let idx = _task.intervalMs > 0
        ? Math.ceil(elapsed / _task.intervalMs)
        : _task.text.length;
    idx = Math.max(0, Math.min(idx, _task.text.length));

    const content = _task.base + _task.text.slice(0, idx);
    // 内容没变不写 DOM，避免重排
    if (subtitleEl.textContent !== content) {
        subtitleEl.textContent = content;
    }
    return idx >= _task.text.length;
}

// 取消 rAF 和兜底定时器
function _cancelSchedulers() {
    if (_rafId !== null) {
        cancelAnimationFrame(_rafId);
        _rafId = null;
    }
    if (_fallbackTimer !== null) {
        clearTimeout(_fallbackTimer);
        _fallbackTimer = null;
    }
}

// 同时最多挂 1 个 rAF + 1 个定时器，防回调累积卡死
function _scheduleTick() {
    if (_rafId !== null || _fallbackTimer !== null) return; // 已挂则不重复
    if (typeof requestAnimationFrame === "function") {
        _rafId = requestAnimationFrame(_tick);
    }
    // rAF 可能停摆，定时器兜底
    _fallbackTimer = setTimeout(_tick, 1000);
}

// 是否还有渲染/清屏工作没做完
function _hasPendingWork() {
    if (!_task) return false;
    if (_task.clearAt !== null) return true; // 清屏未执行
    return _now() - _task.startTime < _task.intervalMs * _task.text.length;
}

function _tick() {
    // 取消另一个，保持回调数恒定
    _cancelSchedulers();
    if (!_task) return;

    _render();

    // 按绝对时间清屏，抗节流
    if (_task.clearAt !== null && _now() >= _task.clearAt) {
        _task = null;
        subtitleEl.textContent = "";
        return;
    }

    // 显示完且无待清屏则停止空转
    if (!_hasPendingWork()) return;

    _scheduleTick();
}

function _stopTick() {
    _cancelSchedulers();
}

function display_subtitle(text, duration, is_head = false, is_tail = false) {
    // 重复文本直接丢弃，防 base 累加重叠
    if (!is_head && _task && _task.text === text) {
        return;
    }

    _stopTick();

    // 换字幕清掉上一条任务
    _task = null;

    if (is_head) {
        subtitleEl.textContent = "";
    }

    console.log(text + "\n" + duration);

    if (!text || !(duration > 0)) {
        return;
    }

    // 每个字符显示的时间（毫秒）
    const intervalMs = (duration * 1000) / text.length;

    // base 超长只保留尾部，防越来越卡
    let base = subtitleEl.textContent || "";
    if (base.length > 40) {
        subtitleEl.textContent = "";
        base = "";
    }
    

    _task = {
        base: base,
        text: text,
        intervalMs: intervalMs,
        startTime: _now(),
        clearAt: is_tail ? _now() + (duration + 1) * 1000 : null,
    };

    _render();        // 立即渲染一次
    _scheduleTick();
}

function clear_subtitle() {
    _stopTick();
    _task = null;
    subtitleEl.textContent = "";
}

// 恢复可见立刻补齐字幕
document.addEventListener("visibilitychange", () => {
    if (!document.hidden) {
        if (_task && _hasPendingWork()) {
            _render();
            _scheduleTick();
        }
        // 恢复时确保 WS 连着
        if (!ws || ws.readyState !== WebSocket.OPEN) {
            _connectWS();
        }
    }
});

// freeze 恢复时补连并补齐字幕
document.addEventListener("resume", () => {
    if (_task && _hasPendingWork()) {
        _render();
        _scheduleTick();
    }
    if (!ws || ws.readyState !== WebSocket.OPEN) {
        _connectWS();
    }
});

const _UNIQUE_NAME = "momo_subtitle";
let ws = null;
let _wsReconnectTimer = null;
let _wsClosedByUs = false;

function _connectWS() {
    // 连接在走就不重建（CLOSING 也要挡）
    if (ws && ws.readyState !== WebSocket.CLOSED) {
        return;
    }

    ws = new WebSocket("ws://127.0.0.1:5050/ws");

    ws.onopen = () => {
        console.log("Momo MCP Server connected");
        // 注册自己，重连也要重注
        ws.send(JSON.stringify({
            unique_name: _UNIQUE_NAME
        }));
    };

    ws.onmessage = (event) => {
        console.log("收到 Momo 字幕信息:", event.data);
        let data;
        try {
            data = JSON.parse(event.data);
        } catch (e) {
            // 解析失败不打断消息处理
            console.log("Momo 字幕信息解析失败:", e);
            return;
        }
        const action = data.action;

        if (action == "display") {
            display_subtitle(data.text, data.duration, data.is_head, data.is_tail);
        }
        if (action == "clear") {
            clear_subtitle();
        }
    };

    ws.onerror = () => {
        // 重连统一在 onclose 处理
        console.log("Momo DrawBridge Server error");
    };

    ws.onclose = (event) => {
        console.log("Momo DrawBridge Server disconnected, code=" + event.code +
            " reason=" + event.reason);
        if (_wsClosedByUs) {
            console.log("Momo DrawBridge Server disconnected (by us)");
            return;
        }
        console.log("Momo DrawBridge Server disconnected, retrying...");
        _scheduleReconnect();
    };
}

// 断线 2 秒后重连
function _scheduleReconnect() {
    if (_wsReconnectTimer !== null) return;
    _wsReconnectTimer = setTimeout(() => {
        _wsReconnectTimer = null;
        _connectWS();
    }, 2000);
}

// 看门狗：定期探活，冻结恢复后补连
function _startWatchdog() {
    setInterval(() => {
        if (!ws || ws.readyState !== WebSocket.OPEN) {
            if (_wsReconnectTimer === null) {
                console.log("watchdog: 连接不在 OPEN 状态，尝试重连");
                _connectWS();
            }
        }
    }, 3000);
}

// 应用层心跳，文本消息保活
function _startHeartbeat(intervalMs) {
    setInterval(() => {
        if (ws && ws.readyState === WebSocket.OPEN) {
            try {
                ws.send(JSON.stringify({ action: "ping", t: Date.now() }));
                console.log("heartbeat ping sent");
            } catch (e) {
                console.log("heartbeat send failed:", e);
            }
        }
    }, intervalMs);
}

_connectWS();
_startWatchdog();
_startHeartbeat(15000);