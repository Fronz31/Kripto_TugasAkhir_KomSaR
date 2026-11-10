"""Baca/tulis file dongle KOMSAR.DONGLE di flashdisk (Windows, via ctypes)."""

import base64
import binascii
import ctypes
import json
import os
import uuid

DONGLE_FILE = "KOMSAR.DONGLE"
DRIVE_REMOVABLE = 2


def list_removable_drives():
    """Daftar root drive removable, mis. ["E:\\"]."""
    k32 = ctypes.windll.kernel32
    mask = k32.GetLogicalDrives()
    drives = [f"{chr(65 + i)}:\\" for i in range(26) if mask >> i & 1]
    return [d for d in drives if k32.GetDriveTypeW(d) == DRIVE_REMOVABLE]


def volume_serial(drive):
    """Serial volume sebagai 8 hex uppercase, atau None bila gagal."""
    serial = ctypes.c_uint32()
    ok = ctypes.windll.kernel32.GetVolumeInformationW(
        ctypes.c_wchar_p(drive), None, 0, ctypes.byref(serial), None, None, None, 0
    )
    return f"{serial.value:08X}" if ok else None


def _valid(dongle_id, token):
    try:
        uuid.UUID(str(dongle_id))
        return len(base64.b64decode(token, validate=True)) == 32
    except (ValueError, TypeError, binascii.Error):
        return False


def read_dongle(drives=list_removable_drives, serial_of=volume_serial):
    """Dongle valid pertama di drive removable, atau None."""
    for drive in drives():
        try:
            with open(os.path.join(drive, DONGLE_FILE), encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict) or data.get("v") != 1:
            continue
        if not _valid(data.get("dongle_id"), data.get("token")):
            continue
        serial = serial_of(drive)
        if serial is None:
            continue
        return {"dongle_id": data["dongle_id"], "token": data["token"], "volume_serial": serial}
    return None


def write_dongle(drive, dongle_id, token, drives=list_removable_drives):
    """Tulis KOMSAR.DONGLE ke root drive removable. Return True bila berhasil."""
    # Drive berasal dari JS halaman: hanya izinkan drive removable yang terdeteksi.
    if drive not in drives():
        raise ValueError("Drive bukan flashdisk removable")
    if not _valid(dongle_id, token):
        raise ValueError("dongle_id atau token tidak valid")
    path = os.path.join(drive, DONGLE_FILE)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"v": 1, "dongle_id": dongle_id, "token": token}, f)
    os.replace(tmp, path)
    return True
