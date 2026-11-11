// Alur login KomSaR (aplikasi desktop / pywebview). Butuh app.js; halaman suara juga butuh voice.js.
(function () {
  function hasDesktop() { return !!(window.pywebview && window.pywebview.api); }

  // ---- Langkah 1: username + password + bukti dongle ----
  var form = document.getElementById("login-form");
  if (form) {
    var note = document.getElementById("desktop-only");
    var btn = form.querySelector("button[type=submit]");
    var needDongle = form.getAttribute("data-require-dongle") === "1";
    if (needDongle && !hasDesktop()) {
      note.classList.remove("hidden");
      btn.disabled = true;
      window.komsar.whenDesktop(function () { note.classList.add("hidden"); btn.disabled = false; });
    }
    form.addEventListener("submit", function (e) {
      if (!needDongle) return;
      e.preventDefault();
      if (!hasDesktop()) { note.classList.remove("hidden"); return; }
      btn.disabled = true;
      window.pywebview.api.read_dongle().then(function (d) {
        if (!d || d.error) throw new Error("Dongle tidak terbaca. Colokkan dongle KomSaR lalu coba lagi.");
        form.elements.dongle_id.value = d.dongle_id;
        form.elements.token.value = d.token;
        form.elements.volume_serial.value = d.volume_serial;
        form.submit();
      }).catch(function (err) {
        note.textContent = err.message; note.classList.remove("hidden"); btn.disabled = false;
      });
    });
  }

  // ---- Langkah 2: verifikasi suara / pendaftaran suara login pertama ----
  var start = document.getElementById("voice-start");
  if (!start || !window.komsarVoice) return;
  var phrase = document.getElementById("voice-phrase");
  var status = document.getElementById("voice-status");
  var label = document.getElementById("voice-label");
  var timer = document.getElementById("voice-timer");
  var progress = document.getElementById("voice-progress");
  var enrolling = !!document.getElementById("voice-enroll");
  var V = window.komsarVoice;
  var HOLD = "Tahan untuk merekam", MAX_SECONDS = 10;
  var holdMode = false, running = false;
  var say = function (t) { status.textContent = t; };

  function show(p, i, total, seconds) {
    phrase.textContent = "“" + p + "”";
    if (progress) progress.textContent = total > 1 ? "Rekaman " + (i + 1) + " dari " + total : "";
    say(holdMode ? "Tahan tombol sambil mengucapkan kalimat di atas, lalu lepas."
                 : "Merekam " + seconds + " detik… ucapkan sekarang.");
  }

  // ---- tahan untuk merekam (exe baru: start_recording/stop_recording) ----
  var waiting = null;   // resolve() sampel yang sedang ditunggu; null = tombol tidak menerima rekaman
  var recording = false, starting = null, tick = 0;

  function ready(on) {
    start.setAttribute("aria-disabled", on ? "false" : "true");
    if (on) label.textContent = HOLD;
  }

  function setRecording(on) {
    recording = on;
    start.classList.toggle("recording", on);
    start.setAttribute("aria-pressed", on ? "true" : "false");
    label.textContent = on ? "Merekam… lepas untuk berhenti" : HOLD;
    clearInterval(tick);
    timer.textContent = "";
    if (!on) return;
    var t0 = Date.now();
    var update = function () {
      var s = Math.min(MAX_SECONDS, Math.floor((Date.now() - t0) / 1000));
      timer.textContent = "0:" + (s < 10 ? "0" : "") + s + " / 0:" + MAX_SECONDS;
      if (s >= MAX_SECONDS) release();   // desktop berhenti sendiri di 10 detik: langsung kirim
    };
    update();
    tick = setInterval(update, 200);
  }

  function press(e) {
    if (recording) return;
    if (!waiting) { if (!running) run(); return; }   // setelah gagal: tekan untuk kalimat baru
    if (e.pointerId !== undefined) start.setPointerCapture(e.pointerId);
    setRecording(true);
    say("Merekam… lepas untuk berhenti.");
    starting = window.pywebview.api.start_recording();
  }

  function release() {
    if (!recording) return;
    setRecording(false);
    var done = waiting;
    waiting = null;   // cegah kirim ganda
    ready(false);
    label.textContent = "Mengirim…";
    say("Mengirim…");
    starting.then(function (r) {
      if (r && r.error) throw new Error(r.error);
      return window.pywebview.api.stop_recording();
    }).then(function (wav) {
      if (!wav || wav.error) throw new Error((wav && wav.error) || "Gagal merekam suara.");
      done(wav);
    }).catch(function (err) {   // mis. terlalu pendek: tahan lagi untuk kalimat yang sama
      say(err.message);
      waiting = done;
      ready(true);
    });
  }

  function hold() {
    return new Promise(function (resolve) { waiting = resolve; ready(true); });
  }

  function isHoldKey(e) { return e.key === " " || e.key === "Enter"; }

  function setupHold() {
    holdMode = true;
    start.addEventListener("pointerdown", function (e) { if (e.button === 0) press(e); });
    ["pointerup", "pointercancel", "pointerleave", "blur"].forEach(function (t) { start.addEventListener(t, release); });
    start.addEventListener("keydown", function (e) {
      if (!isHoldKey(e)) return;
      e.preventDefault();
      if (!e.repeat) press(e);
    });
    start.addEventListener("keyup", function (e) { if (isHoldKey(e)) { e.preventDefault(); release(); } });
    start.addEventListener("contextmenu", function (e) { e.preventDefault(); });   // tekan lama di layar sentuh
  }

  // ---- satu putaran verifikasi / pendaftaran ----
  function run() {
    running = true;
    if (holdMode) ready(false); else start.disabled = true;
    var flow = enrolling ? V.enroll({ show: show, hold: hold }) : V.verify({ show: show, hold: hold });
    flow.then(function (ok) {
      running = false;
      if (ok) { say("Berhasil. Membuka dashboard..."); window.location.href = "/dashboard"; return; }
      say("Suara tidak cocok. Coba lagi."); idle();
    }).catch(function (err) {
      running = false;
      say(err.message); idle();
    });
  }

  function idle() {
    if (!holdMode) { start.disabled = false; return; }
    start.setAttribute("aria-disabled", "false");
    label.textContent = "Coba lagi";
  }

  start.addEventListener("click", function () {
    if (!hasDesktop()) say(V.DESKTOP_ONLY);
    else if (!holdMode && !running) run();
  });
  window.komsar.whenDesktop(function () {
    if (V.canHold()) { setupHold(); run(); return; }
    // exe lama tanpa start_recording: klik sekali, rekam durasi tetap
    start.classList.add("plain");
    label.textContent = enrolling ? "Mulai rekam" : "Rekam suara";
  });
})();
