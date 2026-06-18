"""
Scraper data pustaka dari OPAC Amikom (https://opac.amikom.ac.id/).
Mengambil data via API POST dengan paginasi hingga jumlah target tercapai.
"""

import argparse
import csv
import os
import time
from typing import Any

import requests

URL_API = "https://opac.amikom.ac.id/api/opac"
OUTPUT_FILE = "daftar_buku_amikom.csv"
CSV_COLUMNS = ["No", "Judul Buku", "Pengarang", "Rak", "Jumlah Eksemplar", "Status"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/148.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://opac.amikom.ac.id/",
    "X-Requested-With": "XMLHttpRequest",
    "x-api-key": "qIBHqaqNWgpmXwvqRALrkGbRsGHJYGqINxhI",
    "Content-Type": "application/json",
}

# Urutan pencarian: keyword luas agar cukup untuk 200+ item unik
PENCARIAN_DEFAULT = [
    ("buku", "sistem"),
    ("buku", "informasi"),
    ("buku", "manajemen"),
    ("buku", "komputer"),
    ("buku", "data"),
    ("buku", "ekonomi"),
    ("buku", "pendidikan"),
    ("buku", "teknologi"),
    ("jurnal", "sistem"),
    ("jurnal", "informasi"),
    ("jurnal", "komputer"),
    ("prosiding", "sistem"),
]


def fetch_halaman(
    objek: str,
    kata_kunci: str,
    page_number: int,
    page_size: int = 50,
    kolom: str = "judul",
) -> dict[str, Any]:
    payload = {
        "objek": objek,
        "kolom": kolom,
        "kata_kunci": kata_kunci,
        "page_number": str(page_number),
        "page_size": page_size,
    }
    response = requests.post(URL_API, headers=HEADERS, json=payload, timeout=45)
    response.raise_for_status()
    return response.json()


def normalisasi_judul(judul: str) -> str:
    return " ".join(str(judul).lower().split())


def item_ke_baris(buku: dict, no: int) -> dict:
    judul = (buku.get("judul") or "Tanpa Judul").strip()
    pengarang = buku.get("pengarang") or "Tidak diketahui"
    rak = buku.get("rak") or "Tidak ada info rak"
    if isinstance(rak, str):
        rak = rak.replace("\r\n", " ").strip()

    tersedia_raw = buku.get("tersedia", 0)
    try:
        tersedia = int(tersedia_raw) if tersedia_raw else 0
    except (TypeError, ValueError):
        tersedia = 0

    return {
        "No": no,
        "Judul Buku": judul,
        "Pengarang": pengarang,
        "Rak": rak,
        "Jumlah Eksemplar": tersedia,
        "Status": "TERSEDIA" if tersedia > 0 else "KOSONG",
    }


def scrape_opac(
    target: int = 200,
    page_size: int = 50,
    delay_detik: float = 0.3,
    simpan_ke: str = OUTPUT_FILE,
    timpa_file: bool = True,
) -> int:
    """
    Ambil `target` buku unik dari OPAC Amikom, simpan ke CSV.
    Returns: jumlah baris yang berhasil disimpan.
    """
    unik: dict[str, dict] = {}  # judul_normal -> baris csv
    urutan_judul: list[str] = []

    print(f"Memulai scraping OPAC Amikom - target: {target} buku unik\n")

    for objek, kata_kunci in PENCARIAN_DEFAULT:
        if len(urutan_judul) >= target:
            break

        page = 1
        pages_count = 1

        while page <= pages_count and len(urutan_judul) < target:
            try:
                data = fetch_halaman(objek, kata_kunci, page, page_size)
            except requests.RequestException as exc:
                print(f"  [ERROR] {objek}/{kata_kunci} hal {page}: {exc}")
                break

            pages_count = int(data.get("pages_count") or 1)
            items_count = data.get("items_count", "?")
            hasil = data.get("results") or []

            if not hasil:
                break

            baru = 0
            for buku in hasil:
                judul = (buku.get("judul") or "").strip()
                if not judul:
                    continue
                key = normalisasi_judul(judul)
                if key in unik:
                    continue
                urutan_judul.append(key)
                unik[key] = item_ke_baris(buku, len(urutan_judul))
                baru += 1
                if len(urutan_judul) >= target:
                    break

            print(
                f"  [{objek}] '{kata_kunci}' hal {page}/{pages_count} "
                f"(total katalog: {items_count}) -> +{baru} baru, "
                f"kumulatif: {len(urutan_judul)}/{target}"
            )

            page += 1
            time.sleep(delay_detik)

    if len(urutan_judul) < target:
        print(
            f"\nPeringatan: hanya {len(urutan_judul)} buku unik ditemukan "
            f"(target {target})."
        )

    baris = [unik[k] for k in urutan_judul[:target]]
    for i, row in enumerate(baris, start=1):
        row["No"] = i

    mode = "w" if timpa_file or not os.path.isfile(simpan_ke) else "w"
    with open(simpan_ke, mode=mode, encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(baris)

    print(f"\nSelesai! {len(baris)} buku disimpan ke: {os.path.abspath(simpan_ke)}")
    return len(baris)


def scrape_pencarian_post():
    """Fungsi lama — tetap dipanggil untuk kompatibilitas (1 halaman)."""
    return scrape_opac(target=20, timpa_file=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape data OPAC Amikom ke CSV")
    parser.add_argument(
        "-n", "--jumlah",
        type=int,
        default=200,
        help="Jumlah buku unik yang diambil (default: 200)",
    )
    parser.add_argument(
        "-o", "--output",
        default=OUTPUT_FILE,
        help=f"File CSV output (default: {OUTPUT_FILE})",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=50,
        help="Item per halaman API (default: 50)",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Tambahkan ke CSV (default: timpa file)",
    )
    args = parser.parse_args()

    scrape_opac(
        target=args.jumlah,
        page_size=args.page_size,
        simpan_ke=args.output,
        timpa_file=not args.append,
    )
