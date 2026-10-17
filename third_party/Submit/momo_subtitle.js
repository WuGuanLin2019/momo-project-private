// ---------- 字幕：基于时间的渲染（抗浏览器后台/失焦节流） ----------
// 背景：失焦或后台标签页里 setInterval/rAF 会被浏览器节流（1s 甚至 1min），
// 逐字累加的写法会表现为"字幕不动了"。改成按 elapsed 计算索引后，
// 节流只会让刷新变"跳字"，不会丢字、不会卡死、也不会和音频脱节。

const subtitleEl =
    typeof subtitle !== "undefined" && subtitle
        ? subtitle
        : document.getElementById("subtitle");

let _rafId = null;        // 可见时用 rAF，流畅
let _fallbackTimer = null;// 不可见时 rAF 被暂停，用定时器兜底
let _task = null;         // { base, text, intervalMs, startTime, clearAt }

function _now() {
    return typeof performance !== "undefined" && performance.now
        ? performance.now()
        : Date.now();
}

// 按"已经过了多久"算应该显示到第几个字
function _render() {
    if (!_task) return true;

    const elapsed = _now() - _task.startTime;
    let idx = _task.intervalMs > 0
        ? Math.ceil(elapsed / _task.intervalMs)
        : _task.text.length;
    idx = Math.max(0, Math.min(idx, _task.text.length));

    subtitleEl.textContent = _task.base + _task.text.slice(0, idx);
    return idx >= _task.text.length;
}

function _scheduleTick() {
    if (typeof requestAnimationFrame === "function" && _rafId === null) {
        _rafId = requestAnimationFrame(_tick);
    }
    if (_fallbackTimer === null) {
        _fallbackTimer = setTimeout(_tick, 1000);
    }
}

function _tick() {
    _rafId = null;
    _fallbackTimer = null;
    if (!_task) return;

    _render();

    // 清屏也用绝对时间判断，避免被节流后延迟太久
    if (_task.clearAt !== null && _now() >= _task.clearAt) {
        _task = null;
        subtitleEl.textContent = "";
        return;
    }

    _scheduleTick();
}

function _stopTick() {
    if (_rafId !== null) {
        cancelAnimationFrame(_rafId);
        _rafId = null;
    }
    if (_fallbackTimer !== null) {
        clearTimeout(_fallbackTimer);
        _fallbackTimer = null;
    }
}

function display_subtitle(text, duration, is_head = false, is_tail = false) {
    _stopTick();

    // 换字幕时清掉上一条任务（原写法漏了清 _clearTimer，上一条的清屏会把新字幕抹掉）
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

    _task = {
        base: subtitleEl.textContent || "", // 非首句时保留已显示内容，继续往后追加
        text: text,
        intervalMs: intervalMs,
        startTime: _now(),
        clearAt: is_tail ? _now() + (duration + 1) * 1000 : null,
    };

    _render();        // 立刻渲染一次，避免等第一个 tick 才出字
    _scheduleTick();
}

function clear_subtitle() {
    _stopTick();
    _task = null;
    subtitleEl.textContent = "";
}

// 页面重新可见时立刻补齐，避免"切回来还停在几个字"
document.addEventListener("visibilitychange", () => {
    if (!document.hidden && _task) {
        _render();
        _scheduleTick();
    }
});

const _UNIQUE_NAME = "momo_subtitle";
const ws = new WebSocket("ws://127.0.0.1:5050/ws");

ws.onopen = () => {
    // 注册自己
    ws.send(JSON.stringify({
        unique_name: _UNIQUE_NAME
    }));
};

ws.onmessage = (event) => {
    console.log("收到 Momo 字幕信息:", event.data);
    const data = JSON.parse(event.data);
    const action = data.action;

    if(action == "display"){
        display_subtitle(data.text,data.duration,data.is_head,data.is_tail);
    }
    if(action == "clear"){
        clear_subtitle();
    }
};

ws.onclose = () => {
    console.log("Momo MCP Server disconnected");
};