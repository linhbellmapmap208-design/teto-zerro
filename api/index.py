import base64
import json
import os

import requests
from flask import Flask, Response, request

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Provider calls (server-side, keeps API keys off the client)
# ---------------------------------------------------------------------------

def call_gemini(api_key, model, messages):
    contents = []
    for m in messages:
        if m.get("role") == "system":
            continue
        parts = []
        image = m.get("image")
        if image:
            header, _, b64data = image.partition(",")
            mime = "image/png"
            if header.startswith("data:") and ";base64" in header:
                mime = header[len("data:"):header.index(";base64")]
            parts.append({"inline_data": {"mime_type": mime, "data": b64data}})
        if m.get("text"):
            parts.append({"text": m["text"]})
        contents.append({
            "role": "model" if m.get("role") == "assistant" else "user",
            "parts": parts,
        })

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    res = requests.post(url, json={"contents": contents}, timeout=60)
    if not res.ok:
        raise RuntimeError(f"Gemini API loi ({res.status_code}): {res.text[:500]}")

    data = res.json()
    candidates = data.get("candidates") or []
    if not candidates:
        reason = data.get("promptFeedback", {}).get("blockReason")
        raise RuntimeError(f"Gemini khong tra ve noi dung. ({reason or 'khong ro ly do'})")
    parts = candidates[0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in parts)


def call_glm(api_key, model, messages):
    has_image = any(m.get("image") for m in messages)
    resolved_model = model or ("glm-4v-plus" if has_image else "glm-4-plus")

    glm_messages = []
    for m in messages:
        if m.get("role") == "system":
            continue
        image = m.get("image")
        if image:
            glm_messages.append({
                "role": m["role"],
                "content": [
                    {"type": "image_url", "image_url": {"url": image}},
                    {"type": "text", "text": m.get("text", "")},
                ],
            })
        else:
            glm_messages.append({"role": m["role"], "content": m.get("text", "")})

    res = requests.post(
        "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": resolved_model, "messages": glm_messages, "stream": False},
        timeout=60,
    )
    if not res.ok:
        raise RuntimeError(f"GLM API loi ({res.status_code}): {res.text[:500]}")

    data = res.json()
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("GLM khong tra ve noi dung.")
    return choices[0]["message"]["content"]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/api/chat", methods=["POST"])
def chat():
    try:
        body = request.get_json(force=True)
        provider = body.get("provider")
        model = body.get("model")
        messages = body.get("messages") or []
        client_key = body.get("apiKey")

        if provider not in ("gemini", "glm"):
            return Response("Thieu provider hop le.", status=400)

        env_key = os.environ.get("GEMINI_API_KEY") if provider == "gemini" else os.environ.get("GLM_API_KEY")
        api_key = client_key or env_key
        if not api_key:
            return Response(
                f"Chua co API key cho {provider}. Nhap key trong phan Cai dat, "
                f"hoac dat bien moi truong tren Vercel.",
                status=401,
            )

        if provider == "gemini":
            text = call_gemini(api_key, model, messages)
        else:
            text = call_glm(api_key, model, messages)

        return Response(json.dumps({"text": text}), mimetype="application/json")
    except Exception as err:  # noqa: BLE001
        return Response(str(err), status=500)


@app.route("/")
def index():
    return Response(HTML_PAGE, mimetype="text/html")


# ---------------------------------------------------------------------------
# Front-end (single page, no build step: plain HTML/CSS/JS)
# ---------------------------------------------------------------------------

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>AI Chat — Gemini &amp; GLM</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/marked/12.0.2/marked.min.js"></script>
<style>
  :root {
    --cream: #F4F1EA;
    --clay: #D97757;
    --clay-dark: #BF6248;
    --ink: #2B2A27;
    --stone: #E8E4DA;
    --stone-dark: #D8D3C6;
  }
  * { box-sizing: border-box; }
  html, body { height: 100%; margin: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    color: var(--ink);
    background: #fff;
  }
  #app { display: flex; height: 100vh; }

  /* sidebar */
  #sidebar {
    width: 280px;
    flex-shrink: 0;
    background: var(--cream);
    border-right: 1px solid var(--stone-dark);
    display: flex;
    flex-direction: column;
    transition: transform 0.2s ease;
  }
  #sidebar-top { padding: 12px; }
  #new-chat-btn {
    width: 100%;
    display: flex;
    align-items: center;
    gap: 8px;
    background: var(--clay);
    color: #fff;
    border: none;
    border-radius: 10px;
    padding: 10px 12px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
  }
  #new-chat-btn:hover { background: var(--clay-dark); }
  #conv-list { flex: 1; overflow-y: auto; padding: 0 8px 8px; }
  .conv-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 4px;
    border-radius: 10px;
    padding: 10px 12px;
    margin-bottom: 4px;
    font-size: 14px;
    cursor: pointer;
    color: rgba(43,42,39,0.75);
  }
  .conv-item:hover { background: var(--stone); }
  .conv-item.active { background: var(--stone-dark); color: var(--ink); }
  .conv-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .conv-del {
    background: none; border: none; color: rgba(43,42,39,0.35);
    cursor: pointer; font-size: 12px; flex-shrink: 0; display: none;
  }
  .conv-item:hover .conv-del { display: block; }
  .conv-del:hover { color: var(--clay); }
  #sidebar-bottom { padding: 12px; border-top: 1px solid var(--stone-dark); font-size: 11px; color: rgba(43,42,39,0.45); }

  /* main */
  #main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
  header {
    display: flex; align-items: center; gap: 12px;
    padding: 12px 16px; border-bottom: 1px solid var(--stone-dark);
  }
  #menu-btn { display: none; background: none; border: none; font-size: 20px; cursor: pointer; color: rgba(43,42,39,0.6); }
  select {
    font-size: 14px; border: 1px solid var(--stone-dark); border-radius: 10px;
    padding: 6px 8px; background: #fff; outline: none;
  }
  select:focus { border-color: var(--clay); }
  #settings-btn {
    margin-left: auto; background: none; border: none; font-size: 18px;
    cursor: pointer; color: rgba(43,42,39,0.5);
  }
  #settings-btn:hover { color: var(--clay); }

  #messages { flex: 1; overflow-y: auto; padding: 24px 0; }
  #messages-inner { max-width: 720px; margin: 0 auto; display: flex; flex-direction: column; gap: 16px; padding: 0 16px; }
  .empty-hint { text-align: center; color: rgba(43,42,39,0.4); font-size: 14px; margin-top: 80px; padding: 0 24px; }

  .msg-row { display: flex; }
  .msg-row.user { justify-content: flex-end; }
  .msg-row.assistant { justify-content: flex-start; }
  .bubble {
    max-width: 75%; border-radius: 16px; padding: 12px 16px;
    font-size: 15px; line-height: 1.6;
  }
  .msg-row.user .bubble { background: var(--clay); color: #fff; white-space: pre-wrap; }
  .msg-row.assistant .bubble { background: var(--stone); color: var(--ink); }
  .bubble img.attach { max-height: 220px; border-radius: 10px; margin-bottom: 8px; display: block; object-fit: contain; }
  .bubble p { margin: 0 0 0.65em 0; }
  .bubble p:last-child { margin-bottom: 0; }
  .bubble pre { background: var(--ink); color: var(--cream); padding: 0.85em 1em; border-radius: 10px; overflow-x: auto; font-size: 0.85em; }
  .bubble code { background: rgba(0,0,0,0.06); padding: 0.1em 0.35em; border-radius: 5px; font-size: 0.88em; }
  .bubble pre code { background: transparent; padding: 0; }

  @keyframes pulse { 0%, 80%, 100% { opacity: .25 } 40% { opacity: 1 } }
  .typing-dot { animation: pulse 1.2s infinite; }

  /* input bar */
  #input-bar { border-top: 1px solid var(--stone-dark); padding: 12px 16px 16px; }
  #input-inner { max-width: 720px; margin: 0 auto; }
  #image-preview {
    display: none; align-items: center; gap: 8px; background: var(--stone);
    border-radius: 10px; padding: 6px 10px; font-size: 12px; margin-bottom: 8px;
    width: fit-content; color: rgba(43,42,39,0.7);
  }
  #image-preview img { height: 36px; width: 36px; object-fit: cover; border-radius: 6px; }
  #image-preview button { background: none; border: none; cursor: pointer; color: rgba(43,42,39,0.4); }
  #input-row {
    display: flex; align-items: flex-end; gap: 8px;
    border: 1px solid var(--stone-dark); border-radius: 18px; padding: 8px 12px;
  }
  #input-row:focus-within { border-color: var(--clay); }
  #attach-btn {
    background: none; border: none; font-size: 18px; cursor: pointer;
    width: 32px; height: 32px; border-radius: 999px; flex-shrink: 0; color: rgba(43,42,39,0.5);
  }
  #attach-btn:hover { background: var(--stone); color: var(--clay); }
  #text-input {
    flex: 1; border: none; outline: none; resize: none; font-size: 15px;
    line-height: 1.5; padding: 4px 0; max-height: 200px; font-family: inherit; background: transparent;
  }
  #send-btn {
    background: var(--clay); color: #fff; border: none; border-radius: 999px;
    width: 32px; height: 32px; flex-shrink: 0; cursor: pointer; font-size: 16px;
  }
  #send-btn:hover { background: var(--clay-dark); }
  #send-btn:disabled { opacity: 0.35; cursor: not-allowed; }

  /* settings modal */
  #settings-overlay {
    display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.4);
    z-index: 40; align-items: center; justify-content: center; padding: 16px;
  }
  #settings-box { background: #fff; border-radius: 16px; width: 100%; max-width: 420px; padding: 20px; }
  #settings-box h2 { margin: 0 0 4px; font-size: 18px; }
  #settings-box p.hint { font-size: 12px; color: rgba(43,42,39,0.55); margin: 0 0 16px; }
  #settings-box label { display: block; font-size: 12px; font-weight: 600; margin-bottom: 4px; color: rgba(43,42,39,0.7); }
  #settings-box input {
    width: 100%; border: 1px solid var(--stone-dark); border-radius: 10px;
    padding: 8px 12px; font-size: 14px; outline: none; margin-bottom: 14px;
  }
  #settings-box input:focus { border-color: var(--clay); }
  #settings-actions { display: flex; justify-content: flex-end; gap: 8px; }
  #settings-actions button { border: none; border-radius: 10px; padding: 8px 14px; font-size: 14px; cursor: pointer; }
  #settings-cancel { background: none; color: rgba(43,42,39,0.6); }
  #settings-cancel:hover { background: var(--stone); }
  #settings-save { background: var(--clay); color: #fff; }
  #settings-save:hover { background: var(--clay-dark); }

  #sidebar-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.3); z-index: 20; }

  @media (max-width: 768px) {
    #sidebar { position: fixed; z-index: 30; top: 0; left: 0; height: 100%; transform: translateX(-100%); }
    #sidebar.open { transform: translateX(0); }
    #menu-btn { display: block; }
  }
</style>
</head>
<body>

<div id="app">
  <div id="sidebar-overlay"></div>
  <aside id="sidebar">
    <div id="sidebar-top">
      <button id="new-chat-btn">
        <span style="font-size:18px;line-height:1;">+</span>
        Cuộc trò chuyện mới
      </button>
    </div>
    <div id="conv-list"></div>
    <div id="sidebar-bottom">Lịch sử được lưu trên trình duyệt của bạn.</div>
  </aside>

  <div id="main">
    <header>
      <button id="menu-btn">&#9776;</button>
      <select id="provider-select">
        <option value="gemini">Gemini</option>
        <option value="glm">GLM (Zhipu)</option>
      </select>
      <select id="model-select"></select>
      <button id="settings-btn" title="Cài đặt API key">&#9881;</button>
    </header>

    <div id="messages"><div id="messages-inner"></div></div>

    <div id="input-bar">
      <div id="input-inner">
        <div id="image-preview">
          <img id="image-preview-img" src="" alt="preview" />
          <span id="image-preview-name"></span>
          <button id="image-remove-btn">&#10005;</button>
        </div>
        <div id="input-row">
          <button id="attach-btn" title="Đính kèm ảnh">&#128206;</button>
          <input type="file" id="file-input" accept="image/*" style="display:none" />
          <textarea id="text-input" rows="1" placeholder="Nhắn gì đó... (Shift+Enter để xuống dòng)"></textarea>
          <button id="send-btn" title="Gửi">&#8593;</button>
        </div>
      </div>
    </div>
  </div>
</div>

<div id="settings-overlay">
  <div id="settings-box">
    <h2>Cài đặt API key</h2>
    <p class="hint">Key được lưu trong trình duyệt của bạn. Để trống nếu đã đặt biến môi trường trên Vercel.</p>
    <label>Gemini API key</label>
    <input id="gemini-key-input" placeholder="AIza..." />
    <label>GLM (Zhipu) API key</label>
    <input id="glm-key-input" placeholder="xxxxxxxx.xxxxxxxx" />
    <div id="settings-actions">
      <button id="settings-cancel">Huỷ</button>
      <button id="settings-save">Lưu</button>
    </div>
  </div>
</div>

<script>
const MODELS = {
  gemini: [
    { id: "gemini-2.0-flash", label: "Gemini 2.0 Flash" },
    { id: "gemini-1.5-pro", label: "Gemini 1.5 Pro" },
    { id: "gemini-1.5-flash", label: "Gemini 1.5 Flash" },
  ],
  glm: [
    { id: "glm-4-plus", label: "GLM-4-Plus" },
    { id: "glm-4v-plus", label: "GLM-4V-Plus (có ảnh)" },
    { id: "glm-4-flash", label: "GLM-4-Flash" },
  ],
};

const CONV_KEY = "aichat_conversations_v1";
const KEYS_KEY = "aichat_apikeys_v1";

function loadConversations() {
  try { return JSON.parse(localStorage.getItem(CONV_KEY)) || []; } catch { return []; }
}
function saveConversations(list) { localStorage.setItem(CONV_KEY, JSON.stringify(list)); }
function loadApiKeys() {
  try { return JSON.parse(localStorage.getItem(KEYS_KEY)) || { gemini: "", glm: "" }; } catch { return { gemini: "", glm: "" }; }
}
function saveApiKeys(keys) { localStorage.setItem(KEYS_KEY, JSON.stringify(keys)); }
function newId() { return Math.random().toString(36).slice(2) + Date.now().toString(36); }

function makeConversation() {
  return {
    id: newId(), title: "", provider: "gemini", model: MODELS.gemini[0].id,
    messages: [], createdAt: Date.now(), updatedAt: Date.now(),
  };
}

let conversations = loadConversations();
let apiKeys = loadApiKeys();
let activeId = null;
let sending = false;
let pendingImage = null; // { dataUrl, name }

if (conversations.length === 0) {
  const c = makeConversation();
  conversations.push(c);
  activeId = c.id;
} else {
  activeId = conversations[0].id;
}

function getActive() { return conversations.find((c) => c.id === activeId); }
function persist() { saveConversations(conversations); }

function renderSidebar() {
  const list = document.getElementById("conv-list");
  list.innerHTML = "";
  const sorted = [...conversations].sort((a, b) => b.updatedAt - a.updatedAt);
  sorted.forEach((c) => {
    const item = document.createElement("div");
    item.className = "conv-item" + (c.id === activeId ? " active" : "");
    item.innerHTML =
      '<span class="conv-title"></span><button class="conv-del">&#10005;</button>';
    item.querySelector(".conv-title").textContent = c.title || "Trò chuyện mới";
    item.addEventListener("click", () => {
      activeId = c.id;
      closeSidebarMobile();
      renderAll();
    });
    item.querySelector(".conv-del").addEventListener("click", (e) => {
      e.stopPropagation();
      deleteConversation(c.id);
    });
    list.appendChild(item);
  });
}

function deleteConversation(id) {
  conversations = conversations.filter((c) => c.id !== id);
  if (id === activeId) {
    if (conversations.length > 0) {
      activeId = conversations[0].id;
    } else {
      const c = makeConversation();
      conversations.push(c);
      activeId = c.id;
    }
  }
  persist();
  renderAll();
}

function renderHeader() {
  const active = getActive();
  document.getElementById("provider-select").value = active.provider;
  const modelSelect = document.getElementById("model-select");
  modelSelect.innerHTML = "";
  MODELS[active.provider].forEach((m) => {
    const opt = document.createElement("option");
    opt.value = m.id;
    opt.textContent = m.label;
    modelSelect.appendChild(opt);
  });
  modelSelect.value = active.model;
}

function renderMessages() {
  const active = getActive();
  const inner = document.getElementById("messages-inner");
  inner.innerHTML = "";
  if (active.messages.length === 0) {
    const hint = document.createElement("div");
    hint.className = "empty-hint";
    hint.textContent = "Bắt đầu trò chuyện. Bạn có thể đính kèm ảnh bằng nút 📎 ở khung nhập bên dưới.";
    inner.appendChild(hint);
    return;
  }
  active.messages.forEach((m) => inner.appendChild(renderMessageEl(m)));
  document.getElementById("messages").scrollTop = document.getElementById("messages").scrollHeight;
}

function renderMessageEl(m) {
  const row = document.createElement("div");
  row.className = "msg-row " + m.role;
  const bubble = document.createElement("div");
  bubble.className = "bubble";

  if (m.image) {
    const img = document.createElement("img");
    img.src = m.image;
    img.className = "attach";
    bubble.appendChild(img);
  }

  const content = document.createElement("div");
  content.className = "content";
  if (m.text) {
    if (m.role === "assistant") {
      content.innerHTML = marked.parse(m.text);
    } else {
      content.textContent = m.text;
    }
  } else if (m.pending) {
    content.innerHTML = '<span class="typing-dot">●</span> <span class="typing-dot" style="animation-delay:.2s">●</span> <span class="typing-dot" style="animation-delay:.4s">●</span>';
  }
  bubble.appendChild(content);
  row.appendChild(bubble);
  return row;
}

function renderAll() {
  renderSidebar();
  renderHeader();
  renderMessages();
}

function closeSidebarMobile() {
  document.getElementById("sidebar").classList.remove("open");
  document.getElementById("sidebar-overlay").style.display = "none";
}

// --- events: sidebar ---
document.getElementById("new-chat-btn").addEventListener("click", () => {
  const c = makeConversation();
  conversations.unshift(c);
  activeId = c.id;
  persist();
  closeSidebarMobile();
  renderAll();
});
document.getElementById("menu-btn").addEventListener("click", () => {
  document.getElementById("sidebar").classList.add("open");
  document.getElementById("sidebar-overlay").style.display = "block";
});
document.getElementById("sidebar-overlay").addEventListener("click", closeSidebarMobile);

// --- events: header selects ---
document.getElementById("provider-select").addEventListener("change", (e) => {
  const active = getActive();
  active.provider = e.target.value;
  active.model = MODELS[active.provider][0].id;
  active.updatedAt = Date.now();
  persist();
  renderHeader();
});
document.getElementById("model-select").addEventListener("change", (e) => {
  const active = getActive();
  active.model = e.target.value;
  active.updatedAt = Date.now();
  persist();
});

// --- events: settings modal ---
document.getElementById("settings-btn").addEventListener("click", () => {
  document.getElementById("gemini-key-input").value = apiKeys.gemini || "";
  document.getElementById("glm-key-input").value = apiKeys.glm || "";
  document.getElementById("settings-overlay").style.display = "flex";
});
document.getElementById("settings-cancel").addEventListener("click", () => {
  document.getElementById("settings-overlay").style.display = "none";
});
document.getElementById("settings-save").addEventListener("click", () => {
  apiKeys = {
    gemini: document.getElementById("gemini-key-input").value.trim(),
    glm: document.getElementById("glm-key-input").value.trim(),
  };
  saveApiKeys(apiKeys);
  document.getElementById("settings-overlay").style.display = "none";
});

// --- events: image attach ---
const fileInput = document.getElementById("file-input");
document.getElementById("attach-btn").addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", () => {
  const file = fileInput.files[0];
  if (!file || !file.type.startsWith("image/")) return;
  const reader = new FileReader();
  reader.onload = () => {
    pendingImage = { dataUrl: reader.result, name: file.name };
    document.getElementById("image-preview-img").src = pendingImage.dataUrl;
    document.getElementById("image-preview-name").textContent = pendingImage.name;
    document.getElementById("image-preview").style.display = "inline-flex";
  };
  reader.readAsDataURL(file);
});
document.getElementById("image-remove-btn").addEventListener("click", () => {
  pendingImage = null;
  fileInput.value = "";
  document.getElementById("image-preview").style.display = "none";
});

// --- events: text input ---
const textInput = document.getElementById("text-input");
textInput.addEventListener("input", () => {
  textInput.style.height = "auto";
  textInput.style.height = Math.min(textInput.scrollHeight, 200) + "px";
});
textInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    handleSend();
  }
});
document.getElementById("send-btn").addEventListener("click", handleSend);

// --- typewriter reveal for assistant reply ---
function typewriter(el, fullText, onDone) {
  let i = 0;
  const speed = fullText.length > 400 ? 2 : 1; // chars per tick, faster for long text
  const tick = () => {
    i += speed;
    el.innerHTML = marked.parse(fullText.slice(0, i));
    document.getElementById("messages").scrollTop = document.getElementById("messages").scrollHeight;
    if (i < fullText.length) {
      requestAnimationFrame(tick);
    } else if (onDone) onDone();
  };
  requestAnimationFrame(tick);
}

async function handleSend() {
  const active = getActive();
  const text = textInput.value.trim();
  const image = pendingImage ? pendingImage.dataUrl : null;
  if (!text && !image) return;
  if (sending) return;
  sending = true;
  document.getElementById("send-btn").disabled = true;

  const userMsg = { role: "user", text, image };
  active.messages.push(userMsg);
  if (!active.title) active.title = text.slice(0, 45) || "Ảnh đính kèm";
  active.updatedAt = Date.now();

  textInput.value = "";
  textInput.style.height = "auto";
  pendingImage = null;
  fileInput.value = "";
  document.getElementById("image-preview").style.display = "none";

  const assistantMsg = { role: "assistant", text: "", pending: true };
  active.messages.push(assistantMsg);
  persist();
  renderAll();

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider: active.provider,
        model: active.model,
        apiKey: apiKeys[active.provider] || undefined,
        messages: active.messages.slice(0, -1),
      }),
    });

    if (!res.ok) {
      const errText = await res.text();
      assistantMsg.text = "⚠️ " + (errText || "Đã có lỗi xảy ra.");
      assistantMsg.pending = false;
      persist();
      renderAll();
      return;
    }

    const data = await res.json();
    assistantMsg.pending = false;
    persist();
    renderAll();

    // find the just-rendered bubble content element and animate it
    const rows = document.querySelectorAll("#messages-inner .msg-row.assistant .content");
    const lastContent = rows[rows.length - 1];
    typewriter(lastContent, data.text || "", () => {
      assistantMsg.text = data.text || "";
      persist();
    });
  } catch (err) {
    assistantMsg.text = "⚠️ Lỗi kết nối: " + String(err.message || err);
    assistantMsg.pending = false;
    persist();
    renderAll();
  } finally {
    sending = false;
    document.getElementById("send-btn").disabled = false;
  }
}

renderAll();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    app.run(debug=True, port=5000)
