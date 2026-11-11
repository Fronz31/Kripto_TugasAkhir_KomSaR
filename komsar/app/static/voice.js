// Rekam & kirim suara lewat aplikasi desktop KomSaR (pywebview). Butuh app.js (window.komsar.postJSON).
// Pemakaian (fase alur login):
//   komsarVoice.enroll(ui).then(...)   // 3 sampel, masing-masing kalimat acak berbeda
//   komsarVoice.verify(ui).then(function (ok) { ... })
// ui.show(phrase, index, total, seconds) dipanggil sebelum tiap rekaman agar kalimat bisa ditampilkan.
// ui.hold() -> Promise<wav base64>: tahan untuk merekam (start_recording/stop_recording). Dipakai bila
// exe mendukungnya (canHold); exe lama tanpa start_recording memakai record_voice(seconds) durasi tetap.
(function () {
  var DESKTOP_ONLY = "Gunakan aplikasi desktop KomSaR untuk merekam suara.";

  function hasDesktop() { return !!(window.pywebview && window.pywebview.api); }
  function canHold() { return hasDesktop() && typeof window.pywebview.api.start_recording === "function"; }

  function record(purpose, seconds, ui, index, total) {
    if (!hasDesktop()) return Promise.reject(new Error(DESKTOP_ONLY));
    return window.komsar.postJSON("/api/voice/challenge", { purpose: purpose }).then(function (c) {
      if (!c.challenge_id) throw new Error(c.error || "Gagal meminta kalimat acak.");
      ui.show(c.phrase, index, total, seconds);
      var wav = canHold() && ui.hold ? ui.hold() : window.pywebview.api.record_voice(seconds).then(function (w) {
        if (!w || w.error) throw new Error((w && w.error) || "Gagal merekam suara.");
        return w;
      });
      return wav.then(function (w) { return { challenge_id: c.challenge_id, wav_b64: w }; });
    });
  }

  window.komsarVoice = {
    DESKTOP_ONLY: DESKTOP_ONLY,
    canHold: canHold,
    enroll: function (ui) {
      var samples = [];
      var step = function (i) {
        if (i === 3) return window.komsar.postJSON("/api/voice/enroll", { samples: samples });
        return record("enroll", 5, ui, i, 3).then(function (s) { samples.push(s); return step(i + 1); });
      };
      return step(0).then(function (r) {
        if (r.ok !== true) throw new Error(r.error || "Pendaftaran suara ditolak.");
        return true;
      });
    },
    verify: function (ui) {
      return record("verify", 4, ui, 0, 1).then(function (s) {
        return window.komsar.postJSON("/api/voice/verify", s);
      }).then(function (r) {
        if (r.error) throw new Error(r.error);
        return r.ok === true;
      });
    }
  };
})();
