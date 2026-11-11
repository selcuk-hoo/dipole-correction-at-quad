"""Ölçüm sürerken bilgisayarın uyumasını engeller (systemd-inhibit).

11 Kasım 2026: KDE 20 dk hareketsizlikte dizüstünü uyuttu; Pico bağlantısı koptu
(motor durdurulamadı) ve güç kaynakları USB sıfırlanınca komut reddetti.
`uykuyu_engelle()` programı systemd-inhibit altında yeniden başlatır; program
kapanınca engel kalkar. systemd-inhibit yoksa (ör. macOS) hiçbir şey yapmaz.
"""
from __future__ import annotations

import os
import shutil
import sys

_ORTAM = "MERKEZLE_UYKU_ENGELLI"


def uykuyu_engelle(neden: str) -> None:
    if os.environ.get(_ORTAM) or shutil.which("systemd-inhibit") is None:
        return
    os.environ[_ORTAM] = "1"
    os.execvp("systemd-inhibit", [
        "systemd-inhibit", "--what=sleep:idle", "--who=" + os.path.basename(sys.argv[0]),
        "--mode=block", "--why=" + neden, sys.executable, *sys.argv,
    ])
