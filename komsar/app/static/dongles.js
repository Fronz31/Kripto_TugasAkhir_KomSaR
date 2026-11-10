// Halaman admin /admin/dongles: daftarkan flashdisk lewat aplikasi desktop KomSaR.
(function () {
  var form = document.getElementById("dongle-form");
  if (!form) return;
  var select = document.getElementById("dongle-drive");
  var label = document.getElementById("dongle-label");
  var btn = document.getElementById("dongle-register");
  var msg = document.getElementById("dongle-msg");
  var say = function (t) { msg.textContent = t; };

  function loadDrives() {
    window.pywebview.api.list_removable_drives().then(function (drives) {
      select.innerHTML = "";
      if (!drives || drives.error) return say((drives && drives.error) || "Gagal membaca flashdisk.");
      drives.forEach(function (d) {
        if (!d.volume_serial) return;          // serial wajib untuk mengikat dongle ke flashdisk
        var o = document.createElement("option");
        o.value = d.drive; o.textContent = d.drive + " (serial " + d.volume_serial + ")";
        o.setAttribute("data-serial", d.volume_serial);
        select.appendChild(o);
      });
      say(select.options.length ? "" : "Tidak ada flashdisk terdeteksi. Colokkan flashdisk lalu muat ulang.");
    });
  }

  btn.addEventListener("click", function () {
    var opt = select.selectedOptions[0];
    if (!opt) return say("Pilih flashdisk terlebih dahulu.");
    if (!label.value.trim()) return say("Isi label dongle.");
    btn.disabled = true; say("Mendaftarkan...");
    window.komsar.postJSON("/api/dongle/register", { label: label.value.trim(), volume_serial: opt.getAttribute("data-serial") })
      .then(function (r) {
        if (!r.dongle_id) throw new Error(r.error || "Pendaftaran ditolak server.");
        return window.pywebview.api.write_dongle(opt.value, r.dongle_id, r.token).then(function (ok) {
          if (ok !== true) {
            throw new Error("Dongle terdaftar (ID " + r.dongle_id + ") tetapi file gagal ditulis ke flashdisk" +
              (ok && ok.error ? ": " + ok.error : "") + ". Nonaktifkan entri baru tersebut lalu coba lagi.");
          }
          say("Dongle berhasil didaftarkan."); location.reload();
        });
      })
      .catch(function (e) { say(e.message); btn.disabled = false; });
  });

  document.getElementById("dongle-refresh").addEventListener("click", loadDrives);
  window.komsar.whenDesktop(function () {
    document.getElementById("dongle-nodesktop").classList.add("hidden");
    form.classList.remove("hidden");
    loadDrives();
  });
})();
