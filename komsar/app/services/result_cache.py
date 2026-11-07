"""Cache hasil dekripsi di MEMORI proses (bukan database, bukan log, bukan cookie).

Dipakai agar isi pesan tetap tampil di chatbox setelah dekripsi berhasil dan agar file hasil dekripsi
dapat diunduh. Dibersihkan saat logout; file kedaluwarsa otomatis.
"""
import secrets
import time
from collections import OrderedDict

TTL_SECONDS = 600
MAX_FILES = 10
MAX_PENDING = 50
MAX_ATTEMPTS = 5


class ResultCache:
    def __init__(self):
        self.texts: dict[tuple[int, str], str] = {}
        self.files: "OrderedDict[str, dict]" = OrderedDict()
        self.pending: "OrderedDict[str, dict]" = OrderedDict()   # langkah 2 dekripsi (ID + kunci hasil ekstraksi)

    def remember(self, user_pk: int, delivery_id: str, result):
        """Teks -> simpan per delivery (None). File -> simpan sementara, kembalikan token unduh."""
        if result.text is not None:
            self.texts[(user_pk, delivery_id)] = result.text
            return None
        self._purge()
        token = secrets.token_urlsafe(16)
        self.files[token] = {"user_pk": user_pk, "name": result.filename, "mime": result.mime,
                             "data": result.data, "expires": time.time() + TTL_SECONDS}
        while len(self.files) > MAX_FILES:
            self.files.popitem(last=False)
        return token

    def get_text(self, user_pk: int, delivery_id: str):
        return self.texts.get((user_pk, delivery_id))

    def get_file(self, token: str, user_pk: int):
        self._purge()
        entry = self.files.get(token)
        return entry if entry and entry["user_pk"] == user_pk else None

    # ---- langkah 2 dekripsi: ID & kunci hasil ekstraksi disimpan di server, bukan di halaman/cookie ----
    def put_pending(self, user_pk: int, delivery_id: str, rid: str, secret: str) -> str:
        self._purge()
        token = secrets.token_urlsafe(16)
        self.pending[token] = {"user_pk": user_pk, "delivery_id": delivery_id, "rid": rid, "secret": secret,
                               "attempts": 0, "expires": time.time() + TTL_SECONDS}
        while len(self.pending) > MAX_PENDING:
            self.pending.popitem(last=False)
        return token

    def get_pending(self, token: str, user_pk: int):
        self._purge()
        entry = self.pending.get(token)
        return entry if entry and entry["user_pk"] == user_pk else None

    def fail_pending(self, token: str) -> bool:
        """Catat kesalahan; True jika masih boleh mencoba, False jika sesi dibatalkan."""
        entry = self.pending.get(token)
        if entry is None:
            return False
        entry["attempts"] += 1
        if entry["attempts"] >= MAX_ATTEMPTS:
            del self.pending[token]
            return False
        return True

    def drop_pending(self, token: str) -> None:
        self.pending.pop(token, None)

    def clear_user(self, user_pk: int) -> None:
        self.texts = {k: v for k, v in self.texts.items() if k[0] != user_pk}
        for store in (self.files, self.pending):
            for t in [t for t, e in store.items() if e["user_pk"] == user_pk]:
                del store[t]

    def _purge(self) -> None:
        now = time.time()
        for store in (self.files, self.pending):
            for t in [t for t, e in store.items() if e["expires"] < now]:
                del store[t]
