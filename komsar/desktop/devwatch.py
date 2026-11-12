"""Event colok/cabut perangkat dari Windows (WM_DEVICECHANGE), pengganti polling flashdisk.

Jendela tersembunyi top-level menerima broadcast WM_DEVICECHANGE (jendela message-only tidak menerimanya).
Di luar Windows, `wait()` hanya menunggu timeout (fallback polling).
"""
import ctypes
import sys
import threading

WM_DEVICECHANGE = 0x0219


class DeviceEvents:
    def __init__(self):
        self._event = threading.Event()
        self.active = False
        if sys.platform == "win32":
            ready = threading.Event()
            threading.Thread(target=self._run, args=(ready,), daemon=True, name="devwatch").start()
            ready.wait(5)

    def wait(self, timeout):
        """True bila ada perubahan perangkat sebelum timeout."""
        fired = self._event.wait(timeout)
        self._event.clear()
        return fired

    def _run(self, ready):
        from ctypes import wintypes as w

        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        lresult = ctypes.c_ssize_t
        wndproc_t = ctypes.WINFUNCTYPE(lresult, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
        user32.DefWindowProcW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
        user32.DefWindowProcW.restype = lresult
        user32.CreateWindowExW.argtypes = [w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD, ctypes.c_int, ctypes.c_int,
                                           ctypes.c_int, ctypes.c_int, w.HWND, w.HMENU, w.HINSTANCE, w.LPVOID]
        user32.CreateWindowExW.restype = w.HWND

        class WNDCLASSW(ctypes.Structure):
            _fields_ = [("style", w.UINT), ("lpfnWndProc", wndproc_t), ("cbClsExtra", ctypes.c_int),
                        ("cbWndExtra", ctypes.c_int), ("hInstance", w.HINSTANCE), ("hIcon", w.HICON),
                        ("hCursor", w.HANDLE), ("hbrBackground", w.HBRUSH), ("lpszMenuName", w.LPCWSTR),
                        ("lpszClassName", w.LPCWSTR)]

        def proc(hwnd, msg, wparam, lparam):
            if msg == WM_DEVICECHANGE:
                self._event.set()       # jenis event tidak diurai: pemanggil membaca ulang dongle
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        self._proc = wndproc_t(proc)    # simpan referensi agar callback tidak di-GC
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSW(lpfnWndProc=self._proc, hInstance=hinst, lpszClassName="KomSaRDevWatch")
        try:
            if not user32.RegisterClassW(ctypes.byref(wc)):
                return
            # Tidak pernah ditampilkan (tanpa ShowWindow), tetap top-level agar menerima broadcast.
            if not user32.CreateWindowExW(0, wc.lpszClassName, "KomSaR", 0, 0, 0, 0, 0, None, None, hinst, None):
                return
            self.active = True
        finally:
            ready.set()
        msg = w.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
