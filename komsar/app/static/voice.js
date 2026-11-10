// Rekam & kirim suara lewat aplikasi desktop KomSaR (pywebview). Butuh app.js (window.komsar.postJSON).
// Pemakaian (fase alur login):
//   komsarVoice.enroll(showPhrase).then(...)   // 3 sampel, masing-masing kalimat acak berbeda
//   komsarVoice.verify(showPhrase).then(function (ok) { ... })
// showPhrase(phrase, index, total) dipanggil sebelum tiap rekaman agar kalimat bisa ditampilkan.
(function () {
  var DESKTOP_ONLY = "Gunakan aplikasi desktop KomSaR untuk merekam suara.";

  function record(purpose, seconds, showPhrase, index, total) {
    if (!(window.pywebview && window.pywebview.api)) return Promise.reject(new Error(DESKTOP_ONLY));
    return window.komsar.postJSON("/api/voice/challenge", { purpose: purpose }).then(function (c) {
      if (!c.challenge_id) throw new Error(c.error || "Gagal meminta kalimat acak.");
      if (showPhrase) showPhrase(c.phrase, index, total);
      return window.pywebview.api.record_voice(seconds).then(function (wav) {
        if (!wav || wav.error) throw new Error((wav && wav.error) || "Gagal merekam suara.");
        return { challenge_id: c.challenge_id, wav_b64: wav };
      });
    });
  }

  window.komsarVoice = {
    DESKTOP_ONLY: DESKTOP_ONLY,
    enroll: function (showPhrase) {
      var samples = [];
      var step = function (i) {
        if (i === 3) return window.komsar.postJSON("/api/voice/enroll", { samples: samples });
        return record("enroll", 5, showPhrase, i, 3).then(function (s) { samples.push(s); return step(i + 1); });
      };
      return step(0).then(function (r) {
        if (r.ok !== true) throw new Error(r.error || "Pendaftaran suara ditolak.");
        return true;
      });
    },
    verify: function (showPhrase) {
      return record("verify", 4, showPhrase, 0, 1).then(function (s) {
        return window.komsar.postJSON("/api/voice/verify", s);
      }).then(function (r) {
        if (r.error) throw new Error(r.error);
        return r.ok === true;
      });
    }
  };
})();
