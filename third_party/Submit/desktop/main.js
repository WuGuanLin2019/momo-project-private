// Electron 主进程：把 ../sub.html（字幕页）包成一个无边框、透明、置顶的桌面浮窗。
// WebSocket 连接逻辑完全沿用 momo_subtitle.js，启动后自动连 ws://127.0.0.1:5050/ws。
//
// 运行：双击 start_momo_sub.bat，或 conda activate momo_sub 后 npm start
//
// 调整位置/大小（直播中可直接按，自动记忆，重启恢复）：
//   Ctrl+Alt+方向键        移动窗口（24px）
//   Ctrl+Alt+Shift+方向键  快速移动（120px，够从主屏甩到副屏）
//   Ctrl+Alt+PageUp/Down   调整窗口高度（±40px）
//   Ctrl+Alt+Home          回到默认位置（主屏底部）
//   Ctrl+Alt+S             切换点击穿透；关掉后可拖动 #debug 区域移动窗口
//   Ctrl+Alt+Q             退出
// 注意：全屏游戏内全局热键可能被游戏吞掉，建议进游戏前调好位置。

const { app, BrowserWindow, screen, globalShortcut } = require("electron");
const fs = require("fs");
const path = require("path");

const STEP = 24;        // 方向键移动步长
const BIG_STEP = 120;   // Shift + 方向键步长
const HEIGHT_STEP = 40; // 调高度步长
const MIN_H = 80;       // 窗口最小高度

let win = null;
let clickThrough = true;
let saveTimer = null;

// 位置/大小记忆文件（%APPDATA%/momo-subtitle-desktop/window-state.json）
const STATE_FILE = path.join(app.getPath("userData"), "window-state.json");

function defaultBounds() {
    const wa = screen.getPrimaryDisplay().workArea;
    return { x: wa.x, y: wa.y + wa.height - 400, width: wa.width, height: 400 };
}

// 读回上次位置；目标显示器已拔掉时回退默认
function loadBounds() {
    try {
        const s = JSON.parse(fs.readFileSync(STATE_FILE, "utf8"));
        if (typeof s.x !== "number" || typeof s.y !== "number" ||
            typeof s.width !== "number" || typeof s.height !== "number") {
            return defaultBounds();
        }
        const onSomeScreen = screen.getAllDisplays().some((d) => {
            const wa = d.workArea;
            return s.x < wa.x + wa.width && s.x + s.width > wa.x &&
                   s.y < wa.y + wa.height && s.y + s.height > wa.y;
        });
        return onSomeScreen ? s : defaultBounds();
    } catch (e) {
        return defaultBounds();
    }
}

// 防抖写入，避免连续移动时频繁落盘
function saveBounds() {
    if (!win) return;
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
        try {
            fs.writeFileSync(STATE_FILE, JSON.stringify(win.getBounds()));
        } catch (e) { /* 存不上不影响使用 */ }
    }, 200);
}

function nudge(dx, dy) {
    const b = win.getBounds();
    win.setBounds({ ...b, x: b.x + dx, y: b.y + dy });
    saveBounds();
}

function resizeHeight(dh) {
    const b = win.getBounds();
    win.setBounds({ ...b, height: Math.max(MIN_H, b.height + dh) });
    saveBounds();
}

// 把当前穿透状态同步到页面：穿透关闭时 body 加 drag-mode，
// 显示出窗口虚线边界和拖动把手（见 sub.html 的 CSS）
function applyDragMode() {
    if (!win || !win.webContents) return;
    win.webContents
        .executeJavaScript(`document.body.classList.toggle("drag-mode", ${!clickThrough})`)
        .catch(() => { /* 页面还没加载完就忽略，did-finish-load 会补上 */ });
}

function registerHotkeys() {
    globalShortcut.register("Ctrl+Alt+Left", () => nudge(-STEP, 0));
    globalShortcut.register("Ctrl+Alt+Right", () => nudge(STEP, 0));
    globalShortcut.register("Ctrl+Alt+Up", () => nudge(0, -STEP));
    globalShortcut.register("Ctrl+Alt+Down", () => nudge(0, STEP));
    globalShortcut.register("Ctrl+Alt+Shift+Left", () => nudge(-BIG_STEP, 0));
    globalShortcut.register("Ctrl+Alt+Shift+Right", () => nudge(BIG_STEP, 0));
    globalShortcut.register("Ctrl+Alt+Shift+Up", () => nudge(0, -BIG_STEP));
    globalShortcut.register("Ctrl+Alt+Shift+Down", () => nudge(0, BIG_STEP));
    globalShortcut.register("Ctrl+Alt+PageUp", () => resizeHeight(-HEIGHT_STEP));
    globalShortcut.register("Ctrl+Alt+PageDown", () => resizeHeight(HEIGHT_STEP));
    globalShortcut.register("Ctrl+Alt+Home", () => {
        win.setBounds(defaultBounds());
        saveBounds();
    });
    globalShortcut.register("Ctrl+Alt+S", () => {
        clickThrough = !clickThrough;
        win.setIgnoreMouseEvents(clickThrough, { forward: true });
        // 关掉穿透时让窗口边界/拖动把手显形，方便抓取移动
        applyDragMode();
    });
    globalShortcut.register("Ctrl+Alt+Q", () => app.quit());
}

function createWindow() {
    win = new BrowserWindow({
        ...loadBounds(),   // 有记忆位置就用，没有则默认主屏底部
        transparent: true, // 透明窗口，配合 sub.html 里 body { background: transparent; }
        frame: false,      // 无边框
        hasShadow: false,
        alwaysOnTop: true, // 置顶，不被其他窗口盖住
        skipTaskbar: true,
        resizable: true,
        focusable: false,
        webPreferences: {
            // 关掉 Chromium 后台节流：窗口被遮挡/失焦时 rAF 和定时器照常运行
            backgroundThrottling: false,
            contextIsolation: true,
            nodeIntegration: false,
        },
    });

    // 默认点击穿透，不挡直播姬/游戏操作
    win.setIgnoreMouseEvents(true, { forward: true });

    // 手动拖动（关掉点击穿透后抓 #debug 区域）也记住位置
    win.on("move", saveBounds);
    win.on("resize", saveBounds);

    win.loadFile(path.join(__dirname, "..", "sub.html"));

    // 页面（重）加载完后同步一次穿透状态，保证 drag-mode 类正确
    win.webContents.on("did-finish-load", applyDragMode);

    registerHotkeys();
}

app.whenReady().then(createWindow);
app.on("window-all-closed", () => app.quit());
