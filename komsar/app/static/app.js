document.addEventListener("submit", function (e) {
  var msg = e.target.getAttribute("data-confirm");
  if (msg && !window.confirm(msg)) e.preventDefault();
});
var kind = document.getElementById("kind-filter");
var target = document.getElementById("delivery-select");
if (kind && target) {
  var apply = function () {
    Array.prototype.forEach.call(target.options, function (o) {
      var hide = kind.value && o.getAttribute("data-kind") !== kind.value;
      o.hidden = hide; o.disabled = hide;
    });
    if (target.selectedOptions[0] && target.selectedOptions[0].disabled) target.selectedIndex = -1;
  };
  kind.addEventListener("change", apply); apply();
}

var preview = document.getElementById("stego-preview");
if (preview && target) {
  target.addEventListener("change", function () {
    if (!target.value) { preview.classList.add("hidden"); return; }
    preview.src = preview.getAttribute("data-url").replace("__ID__", target.value);
    preview.classList.remove("hidden");
  });
}

// ---- Dongle (hanya di aplikasi desktop KomSaR / pywebview) ----
var csrfMeta = document.querySelector('meta[name="csrf-token"]');
window.komsar = {
  postJSON: function (url, body) {
    return fetch(url, {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfMeta ? csrfMeta.content : "" },
      body: JSON.stringify(body)
    }).then(function (r) { return r.json().catch(function () { return {}; }); });
  },
  whenDesktop: function (fn) {
    if (window.pywebview && window.pywebview.api) fn();
    else window.addEventListener("pywebviewready", fn);
  }
};

function forceLogout() {     // /logout hanya menerima POST + CSRF
  var f = document.createElement("form");
  f.method = "post"; f.action = "/logout";
  var i = document.createElement("input");
  i.type = "hidden"; i.name = "csrf_token"; i.value = csrfMeta.content;
  f.appendChild(i); document.body.appendChild(f); f.submit();
}

if (csrfMeta && document.body.getAttribute("data-session") && document.body.getAttribute("data-require-dongle")) {   // hanya setelah login penuh, bukan sesi pending
  window.komsar.whenDesktop(function () {
    var beat = function () {
      window.pywebview.api.read_dongle().then(function (d) {
        if (!d || d.error) return forceLogout();
        return window.komsar.postJSON("/api/dongle/heartbeat", d).then(function (r) {
          if (!r.ok) forceLogout();
        });
      }).catch(function () { /* jaringan putus: server mengunci sesi setelah timeout */ });
    };
    beat();
    setInterval(beat, 30000);
  });
}
