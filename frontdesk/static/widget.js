/* Front Desk chat widget. Drop one script tag on any page:
   <script src="https://HOST/widget.js" data-frontdesk="https://HOST"></script> */
(function () {
  "use strict";
  var me = document.currentScript;
  var base = (me && me.getAttribute("data-frontdesk")) || "";
  var accent = (me && me.getAttribute("data-accent")) || "#0f6e56";
  var cid = null, open = false, busy = false, name = "Front desk";

  var css = "\
.fd-launch{position:fixed;right:20px;bottom:20px;z-index:2147483000;display:flex;align-items:center;gap:10px;background:" + accent + ";color:#fff;border:0;border-radius:999px;padding:14px 20px 14px 16px;font:600 15px/1 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;box-shadow:0 10px 30px rgba(0,0,0,.18);cursor:pointer}\
.fd-launch svg{width:20px;height:20px}\
.fd-panel{position:fixed;right:20px;bottom:88px;z-index:2147483000;width:370px;max-width:calc(100vw - 24px);height:560px;max-height:calc(100vh - 110px);background:#fff;border-radius:18px;box-shadow:0 24px 70px rgba(0,0,0,.22);display:none;flex-direction:column;overflow:hidden;font:15px/1.45 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#1b1f24}\
.fd-panel.open{display:flex}\
.fd-head{background:" + accent + ";color:#fff;padding:14px 16px;display:flex;align-items:center;gap:12px}\
.fd-avatar{width:36px;height:36px;border-radius:50%;background:rgba(255,255,255,.22);display:flex;align-items:center;justify-content:center;font-weight:700}\
.fd-head b{display:block;font-size:15px}.fd-head span{display:block;font-size:12px;opacity:.85}\
.fd-close{margin-left:auto;background:none;border:0;color:#fff;font-size:22px;cursor:pointer;line-height:1}\
.fd-log{flex:1;overflow:auto;padding:16px;display:flex;flex-direction:column;gap:10px;background:#f6f7f9}\
.fd-msg{max-width:84%;padding:10px 13px;border-radius:14px;white-space:pre-wrap;word-wrap:break-word}\
.fd-bot{align-self:flex-start;background:#fff;border:1px solid #e6e8ec;border-bottom-left-radius:4px}\
.fd-user{align-self:flex-end;background:" + accent + ";color:#fff;border-bottom-right-radius:4px}\
.fd-typing{align-self:flex-start;color:#6b7280;font-size:13px;padding:4px 6px}\
.fd-form{display:flex;gap:8px;padding:12px;border-top:1px solid #e6e8ec;background:#fff}\
.fd-form input{flex:1;border:1px solid #d6d9de;border-radius:10px;padding:11px 12px;font:inherit;outline:none}\
.fd-form input:focus{border-color:" + accent + "}\
.fd-form button{background:" + accent + ";color:#fff;border:0;border-radius:10px;padding:0 16px;font:600 14px -apple-system,sans-serif;cursor:pointer}\
.fd-form button:disabled{opacity:.5;cursor:default}\
.fd-foot{font-size:11px;color:#8a919c;text-align:center;padding:0 0 8px;background:#fff}\
@media(max-width:480px){.fd-panel{right:8px;left:8px;width:auto;bottom:80px}}";

  var style = document.createElement("style"); style.textContent = css; document.head.appendChild(style);

  var launch = document.createElement("button");
  launch.className = "fd-launch"; launch.type = "button";
  launch.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg><span>Chat with us</span>';

  var panel = document.createElement("div"); panel.className = "fd-panel";
  panel.innerHTML = '<div class="fd-head"><div class="fd-avatar">R</div><div><b class="fd-name">Front desk</b><span>Online now · usually replies in seconds</span></div><button class="fd-close" type="button" aria-label="Close">×</button></div>' +
    '<div class="fd-log" role="log" aria-live="polite"></div>' +
    '<form class="fd-form"><input type="text" placeholder="Type a message…" autocomplete="off" maxlength="2000" aria-label="Message"><button type="submit">Send</button></form>' +
    '<div class="fd-foot">Powered by AIVETech Front Desk</div>';

  document.body.appendChild(launch); document.body.appendChild(panel);
  var log = panel.querySelector(".fd-log"), form = panel.querySelector(".fd-form"),
      input = form.querySelector("input"), send = form.querySelector("button");

  function add(role, text) {
    var d = document.createElement("div"); d.className = "fd-msg " + (role === "user" ? "fd-user" : "fd-bot");
    d.textContent = text; log.appendChild(d); log.scrollTop = log.scrollHeight; return d;
  }
  function typing(on) {
    var t = log.querySelector(".fd-typing");
    if (on && !t) { t = document.createElement("div"); t.className = "fd-typing"; t.textContent = name + " is typing…"; log.appendChild(t); log.scrollTop = log.scrollHeight; }
    if (!on && t) t.remove();
  }
  function toggle(show) {
    open = show; panel.classList.toggle("open", open);
    if (open) { input.focus(); if (!log.children.length) greet(); }
  }
  function greet() {
    fetch(base + "/api/config").then(function (r) { return r.json(); }).then(function (c) {
      name = c.name || name; panel.querySelector(".fd-name").textContent = c.name || name;
      add("bot", c.greeting);
    }).catch(function () { add("bot", "Hi, how can I help?"); });
  }
  form.addEventListener("submit", function (e) {
    e.preventDefault(); var text = input.value.trim(); if (!text || busy) return;
    add("user", text); input.value = ""; busy = true; send.disabled = true; typing(true);
    fetch(base + "/api/chat", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conversation_id: cid, message: text }) })
      .then(function (r) { return r.json(); })
      .then(function (d) { cid = d.conversation_id; typing(false); add("bot", d.reply); })
      .catch(function () { typing(false); add("bot", "Sorry, something went wrong. Please try again or call us."); })
      .finally(function () { busy = false; send.disabled = false; input.focus(); });
  });
  launch.addEventListener("click", function () { toggle(!open); });
  panel.querySelector(".fd-close").addEventListener("click", function () { toggle(false); });
})();
