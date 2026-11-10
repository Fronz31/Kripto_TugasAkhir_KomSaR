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
  var enrolling = !!document.getElementById("voice-enroll");
  var show = function (p, i, total) {
    phrase.textContent = "“" + p + "”";
    status.textContent = total > 1 ? "Rekaman " + (i + 1) + " dari " + total + "... ucapkan sekarang." : "Merekam... ucapkan sekarang.";
  };
  start.addEventListener("click", function () {
    if (!hasDesktop()) { status.textContent = window.komsarVoice.DESKTOP_ONLY; return; }
    start.disabled = true;
    var run = enrolling ? window.komsarVoice.enroll(show) : window.komsarVoice.verify(show);
    run.then(function (ok) {
      if (ok) { status.textContent = "Berhasil. Membuka dashboard..."; window.location.href = "/dashboard"; return; }
      status.textContent = "Suara tidak cocok. Coba lagi."; start.disabled = false;
    }).catch(function (err) {
      status.textContent = err.message; start.disabled = false;
    });
  });
})();
