"""PLACEHOLDER Biometric Face Recognition.

Belum diimplementasikan dan TIDAK mensimulasikan autentikasi biometrik.
Antarmuka disiapkan agar dapat ditambahkan pada pengembangan berikutnya.
"""


class BiometricAuthenticator:
    available = False

    def verify(self, user, sample) -> bool:
        raise NotImplementedError("Autentikasi biometrik belum diimplementasikan.")
