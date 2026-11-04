"""Firmware'deki enkoder paketi CRC'sinin bilgisayarda testi.

test_firmware/enkoder_crc_testi.cpp, stator'un paket kurulumunu, RS485
ayrıştırıcısını ve rotorun CRC kontrolünü aynen kullanır; bütün 1-3 bitlik
hataları dener. Pico SDK gerekmez, yalnızca g++.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

DONEN_BOBIN = Path(__file__).resolve().parents[2]
KAYNAK = DONEN_BOBIN / "test_firmware" / "enkoder_crc_testi.cpp"


def _derle_calistir(tmp_path: Path, *ek: str) -> subprocess.CompletedProcess:
    cikti = tmp_path / "enkoder_crc_testi"
    subprocess.run(
        ["g++", "-std=c++17", "-Wall", "-Werror", f"-I{DONEN_BOBIN / 'include'}", *ek, str(KAYNAK), "-o", str(cikti)],
        check=True, capture_output=True, text=True,
    )
    return subprocess.run([str(cikti)], capture_output=True, text=True, timeout=120)


@pytest.mark.skipif(shutil.which("g++") is None, reason="g++ yok")
def test_bit_hatalari_yanlis_aci_olarak_kabul_edilmez(tmp_path):
    sonuc = _derle_calistir(tmp_path)
    assert sonuc.returncode == 0, sonuc.stdout + sonuc.stderr
    assert "yanlis_kabul=0" in sonuc.stdout


@pytest.mark.skipif(shutil.which("g++") is None, reason="g++ yok")
def test_crc_kontrolu_olmadan_hatalar_gecer(tmp_path):
    # Testin kendisi sınıyor mu: CRC kontrolü kapalıyken yanlış kabuller görülmeli
    sonuc = _derle_calistir(tmp_path, "-DCRC_KONTROLU_KAPALI")
    assert sonuc.returncode == 1 and "yanlis_kabul=0" not in sonuc.stdout
