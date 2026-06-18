"""
Sistem rekomendasi KNN — struktur mengikuti Jendela Book (jendelabook.com):
  1. Produk Terbaru       → koleksi terbaru di beranda
  2. Produk per Kategori  → seperti halaman "Produk Kami"
  3. Produk Terkait       → KNN saat lihat detail buku
  4. Rekomendasi Untuk Anda → personal KNN dari favorit
  5. Seri Terkait         → buku dengan judul/seri mirip (mis. Super Easy Tenses)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neighbors import NearestNeighbors


# ---------------------------------------------------------------------------
# Model data (struktur output seperti Jendela Book)
# ---------------------------------------------------------------------------
@dataclass
class BlokRekomendasi:
    """Satu blok rekomendasi di halaman (judul section + daftar judul buku)."""
    id: str
    judul_section: str
    deskripsi: str
    judul_buku: list[str] = field(default_factory=list)
    metode: str = ""  # knn_hybrid | content_knn | collaborative_knn | kategori | terbaru


@dataclass
class HalamanRekomendasi:
    """Kumpulan blok rekomendasi untuk satu halaman."""
    blok: list[BlokRekomendasi] = field(default_factory=list)

    def tambah(self, blok: BlokRekomendasi) -> None:
        if blok.judul_buku:
            self.blok.append(blok)


# ---------------------------------------------------------------------------
# Utilitas kategori & seri (mirip kategori di Jendela Book)
# ---------------------------------------------------------------------------
def _infer_tipe(rak: str) -> str:
    rak = str(rak).lower()
    if "jurnal" in rak or "prosiding" in rak:
        return "jurnal"
    if "ta/skripsi" in rak or "tesis" in rak or "disertasi" in rak:
        return "ta_skripsi"
    return "buku"


def get_kategori(rak: str, pengarang: str = "") -> str:
    """
    Nama kategori tampilan — analog kategori Jendela Book
    (Self Improvement, Pendidikan, Religi, dll).
    """
    rak = str(rak).strip()
    if not rak or rak.lower() in ("tidak ada info rak", "tidak diketahui"):
        return "Koleksi Umum"
    # Singkat nama rak panjang
    if len(rak) > 45:
        return rak[:42] + "..."
    return rak


def _prefix_seri(judul: str, min_len: int = 12) -> str:
    """Ambil prefix judul untuk deteksi seri (contoh: 'Super Easy Tenses')."""
    judul = re.sub(r"\s+", " ", str(judul).strip())
    # Hapus suffix dalam kurung di akhir: (Past), (Present), dll.
    base = re.sub(r"\s*[\(\[][^)\]]*[\)\]]\s*$", "", judul).strip()
    if len(base) >= min_len:
        return base[: min(len(base), 35)]
    return base.split(":")[0].strip()[:35] if ":" in base else base[:25]


def build_user_item_matrix(df_buku: pd.DataFrame, df_fav: pd.DataFrame) -> pd.DataFrame:
    """Matriks buku x user (untuk item-based CF)."""
    if df_fav.empty:
        return pd.DataFrame(index=df_buku["Judul Buku"].unique())
    df_fav = df_fav.copy()
    df_fav["suka"] = 1
    pivot = df_fav.pivot_table(
        index="judul_buku", columns="username", values="suka", fill_value=0, aggfunc="max"
    )
    return pivot.reindex(df_buku["Judul Buku"].unique(), fill_value=0)


def build_user_book_matrix(df_fav: pd.DataFrame) -> pd.DataFrame:
    """
    Matriks user x buku (untuk user-based CF).
    Baris = pengguna, kolom = judul buku, nilai = 1 jika favorit.
    """
    if df_fav.empty:
        return pd.DataFrame()
    df = df_fav.copy()
    df["rating"] = 1
    return df.pivot_table(
        index="username",
        columns="judul_buku",
        values="rating",
        fill_value=0,
        aggfunc="max",
    )


# ---------------------------------------------------------------------------
# KNN User-Based Collaborative Filtering
# ---------------------------------------------------------------------------
def knn_user_based(
    target_user: str,
    df_fav: pd.DataFrame,
    k_neighbors: int = 3,
    n_rekomendasi: int = 6,
) -> tuple[list[str], list[str], str]:
    """
    User-Based Collaborative Filtering dengan KNN.

    Skenario:
      User A favorit: Buku 1, 2, 3
      User B favorit: Buku 1
      -> User A = nearest neighbor dari User B
      -> Rekomendasi ke User B: Buku 2, 3

    Returns:
      (daftar_judul_rekomendasi, daftar_username_tetangga, metode)
    """
    matriks = build_user_book_matrix(df_fav)

    if target_user not in matriks.index:
        return [], [], "user_knn_tidak_ada_data"

    if len(matriks) < 2:
        return [], [], "user_knn_butuh_2_user"

    favorit_target = set(
        df_fav[df_fav["username"] == target_user]["judul_buku"].tolist()
    )
    if not favorit_target:
        return [], [], "belum_ada_favorit"

    k = min(k_neighbors + 1, len(matriks))
    model = NearestNeighbors(metric="cosine", algorithm="brute", n_neighbors=k)
    model.fit(matriks.values)

    idx = matriks.index.get_loc(target_user)
    jarak, indeks = model.kneighbors(matriks.iloc[idx].values.reshape(1, -1))

    skor_buku: dict[str, float] = {}
    tetangga: list[str] = []

    for pos, d in zip(indeks[0], jarak[0]):
        nama_user = matriks.index[pos]
        if nama_user == target_user:
            continue
        tetangga.append(nama_user)
        bobot = max(0.0, 1.0 - float(d))
        buku_tetangga = df_fav[df_fav["username"] == nama_user]["judul_buku"]
        for buku in buku_tetangga:
            if buku not in favorit_target:
                skor_buku[buku] = skor_buku.get(buku, 0.0) + bobot

    if not skor_buku:
        return [], tetangga, "user_knn_tanpa_overlap"

    urut = sorted(skor_buku.items(), key=lambda x: x[1], reverse=True)
    judul = [b for b, _ in urut[:n_rekomendasi]]
    return judul, tetangga, "user_based_knn"


# ---------------------------------------------------------------------------
# KNN Item-Based (tetangga buku, bukan user)
# ---------------------------------------------------------------------------
def knn_collaborative(
    judul_referensi: str,
    matriks: pd.DataFrame,
    n_neighbors: int = 6,
) -> list[str]:
    if judul_referensi not in matriks.index:
        return []
    if matriks.shape[1] < 1:
        return []

    k = min(n_neighbors + 1, len(matriks))
    if k <= 1:
        return []

    model = NearestNeighbors(metric="cosine", algorithm="brute", n_neighbors=k)
    model.fit(matriks.values)
    idx = matriks.index.get_loc(judul_referensi)
    _, indices = model.kneighbors(matriks.iloc[idx].values.reshape(1, -1))

    hasil = []
    for i in indices[0]:
        judul = matriks.index[i]
        if judul != judul_referensi:
            hasil.append(judul)
    return hasil[: n_neighbors - 1]


def knn_content_based(
    judul_referensi: str,
    df_buku: pd.DataFrame,
    kolom_konten: str = "Konten",
    n_neighbors: int = 6,
) -> list[str]:
    if judul_referensi not in df_buku["Judul Buku"].values:
        return []

    vectorizer = TfidfVectorizer()
    matrix = vectorizer.fit_transform(df_buku[kolom_konten].fillna(""))
    k = min(n_neighbors + 1, len(df_buku))
    model = NearestNeighbors(metric="cosine", algorithm="brute", n_neighbors=k)
    model.fit(matrix)

    idx = df_buku[df_buku["Judul Buku"] == judul_referensi].index[0]
    pos = df_buku.index.get_loc(idx)
    _, indices = model.kneighbors(matrix[pos])

    hasil = []
    for i in indices[0]:
        judul = df_buku.iloc[i]["Judul Buku"]
        if judul != judul_referensi:
            hasil.append(judul)
    return hasil[: n_neighbors - 1]


# ---------------------------------------------------------------------------
# Blok rekomendasi ala Jendela Book
# ---------------------------------------------------------------------------
def produk_terbaru(df_buku: pd.DataFrame, n: int = 6) -> BlokRekomendasi:
    """Section 'Produk Terbaru' di beranda Jendela Book."""
    judul = df_buku.tail(n)["Judul Buku"].tolist()[::-1]
    return BlokRekomendasi(
        id="produk_terbaru",
        judul_section="Produk Terbaru",
        deskripsi="Koleksi pustaka terbaru di perpustakaan.",
        judul_buku=judul,
        metode="terbaru",
    )


def produk_per_kategori(
    df_buku: pd.DataFrame,
    n_per_kategori: int = 4,
    max_kategori: int = 6,
) -> list[BlokRekomendasi]:
    """
    Section per kategori — analog halaman 'Produk Kami' Jendela Book
    (Buku Self Improvement, Buku Anak, Buku Pendidikan, ...).
    """
    df = df_buku.copy()
    df["Kategori"] = df.apply(
        lambda r: get_kategori(r["Rak"], r.get("Pengarang", "")), axis=1
    )
    blok_list: list[BlokRekomendasi] = []
    kategori_urut = df["Kategori"].value_counts().head(max_kategori).index.tolist()

    for kat in kategori_urut:
        sub = df[df["Kategori"] == kat].tail(n_per_kategori)
        if sub.empty:
            continue
        blok_list.append(
            BlokRekomendasi(
                id=f"kategori_{kat[:20]}",
                judul_section=kat,
                deskripsi=f"Pustaka dalam kategori {kat}.",
                judul_buku=sub["Judul Buku"].tolist()[::-1],
                metode="kategori",
            )
        )
    return blok_list


def seri_terkait(
    judul_referensi: str,
    df_buku: pd.DataFrame,
    n: int = 6,
) -> BlokRekomendasi:
    """
    Buku dalam seri yang sama — analog produk seri di Jendela Book
    (mis. Super Easy Tenses Past / Present / Future).
    """
    prefix = _prefix_seri(judul_referensi)
    if len(prefix) < 8:
        return BlokRekomendasi(
            id="seri_terkait",
            judul_section="Seri Terkait",
            deskripsi="",
            judul_buku=[],
            metode="seri",
        )

    mask = df_buku["Judul Buku"].apply(
        lambda j: _prefix_seri(j) == prefix and j != judul_referensi
    )
    seri = df_buku[mask]["Judul Buku"].head(n).tolist()

    return BlokRekomendasi(
        id="seri_terkait",
        judul_section="Seri Terkait",
        deskripsi=f"Buku lain dalam seri yang sama.",
        judul_buku=seri,
        metode="seri",
    )


def lainnya_di_kategori_ini(
    judul_referensi: str,
    df_buku: pd.DataFrame,
    n: int = 6,
) -> BlokRekomendasi:
    """Produk se-kategori — di rak/kategori yang sama."""
    baris = df_buku[df_buku["Judul Buku"] == judul_referensi]
    if baris.empty:
        return BlokRekomendasi(
            id="lainnya_kategori",
            judul_section="Lainnya di Kategori Ini",
            deskripsi="",
            judul_buku=[],
            metode="kategori",
        )
    kat = get_kategori(baris.iloc[0]["Rak"])
    df = df_buku.copy()
    df["Kategori"] = df["Rak"].apply(get_kategori)
    lain = df[(df["Kategori"] == kat) & (df["Judul Buku"] != judul_referensi)]
    judul = lain.tail(n)["Judul Buku"].tolist()[::-1]

    return BlokRekomendasi(
        id="lainnya_kategori",
        judul_section=f"Lainnya di {kat}",
        deskripsi=f"Pustaka lain dalam kategori yang sama.",
        judul_buku=judul,
        metode="kategori",
    )


def produk_terkait(
    judul_referensi: str,
    df_buku: pd.DataFrame,
    df_fav: pd.DataFrame,
    n: int = 6,
) -> BlokRekomendasi:
    """
    Produk terkait di halaman detail — KNN hybrid
    (content + collaborative seperti 'Anda mungkin juga suka').
    """
    matriks = build_user_item_matrix(df_buku, df_fav)
    skor: dict[str, float] = {}
    metode = "content_knn"

    # Prioritas 1: seri sama
    for j in seri_terkait(judul_referensi, df_buku, n).judul_buku:
        skor[j] = skor.get(j, 0) + 3.0

    # Prioritas 2: collaborative KNN
    if judul_referensi in matriks.index and matriks.loc[judul_referensi].sum() > 0:
        for j in knn_collaborative(judul_referensi, matriks, n_neighbors=n + 2):
            skor[j] = skor.get(j, 0) + 2.0
        metode = "collaborative_knn"

    # Prioritas 3: content KNN
    for j in knn_content_based(judul_referensi, df_buku, n_neighbors=n + 2):
        skor[j] = skor.get(j, 0) + 1.5

    # Prioritas 4: se-kategori
    for j in lainnya_di_kategori_ini(judul_referensi, df_buku, n).judul_buku:
        skor[j] = skor.get(j, 0) + 1.0

    skor.pop(judul_referensi, None)
    urut = sorted(skor.items(), key=lambda x: x[1], reverse=True)
    judul_list = [j for j, _ in urut[:n]]

    if not judul_list:
        judul_list = knn_content_based(judul_referensi, df_buku, n_neighbors=n + 1)[:n]
        metode = "content_knn"

    return BlokRekomendasi(
        id="produk_terkait",
        judul_section="Produk Terkait",
        deskripsi="",
        judul_buku=judul_list,
        metode=metode if judul_list else "content_knn",
    )


def rekomendasi_untuk_anda(
    username: str,
    df_buku: pd.DataFrame,
    df_fav: pd.DataFrame,
    n: int = 6,
    k_neighbors: int = 3,
) -> BlokRekomendasi:
    """
    Rekomendasi personal — User-Based Collaborative Filtering + KNN.

    Logika: cari user tetangga terdekat (pola favorit mirip),
    lalu rekomendasikan buku yang disukai tetangga tetapi belum difavorit user ini.
    """
    fav_user = df_fav[df_fav["username"] == username]["judul_buku"].tolist()
    if not fav_user:
        return BlokRekomendasi(
            id="rekomendasi_anda",
            judul_section="Rekomendasi Untuk Anda",
            deskripsi="Tambahkan favorit untuk mendapat saran personal.",
            judul_buku=[],
            metode="belum_ada_favorit",
        )

    # --- Utama: User-Based KNN ---
    judul_list, tetangga, metode = knn_user_based(
        username, df_fav, k_neighbors=k_neighbors, n_rekomendasi=n
    )

    if judul_list:
        return BlokRekomendasi(
            id="rekomendasi_anda",
            judul_section="Rekomendasi Untuk Anda",
            deskripsi="",
            judul_buku=judul_list,
            metode=metode,
        )

    # --- Fallback: Content-Based KNN ---
    terakhir = fav_user[-1]
    judul_list = knn_content_based(terakhir, df_buku, n_neighbors=n + 1)[:n]
    return BlokRekomendasi(
        id="rekomendasi_anda",
        judul_section="Rekomendasi Untuk Anda",
        deskripsi="",
        judul_buku=judul_list,
        metode="content_knn_fallback",
    )


def populer_berdasarkan_favorit(
    df_buku: pd.DataFrame,
    df_fav: pd.DataFrame,
    n: int = 6,
) -> BlokRekomendasi:
    """Produk populer — buku yang paling banyak difavoritkan (social proof)."""
    if df_fav.empty:
        return BlokRekomendasi(
            id="populer",
            judul_section="Populer di Perpustakaan",
            deskripsi="",
            judul_buku=[],
            metode="populer",
        )
    hitung = df_fav["judul_buku"].value_counts().head(n)
    return BlokRekomendasi(
        id="populer",
        judul_section="Populer di Perpustakaan",
        deskripsi="Buku yang paling sering disimpan pengguna.",
        judul_buku=hitung.index.tolist(),
        metode="populer",
    )


# ---------------------------------------------------------------------------
# Builder halaman (struktur lengkap per halaman)
# ---------------------------------------------------------------------------
def halaman_beranda(
    df_buku: pd.DataFrame,
    df_fav: pd.DataFrame,
    username: str | None = None,
) -> HalamanRekomendasi:
    """
    Struktur beranda Jendela Book:
      - Produk Terbaru
      - Rekomendasi Untuk Anda (jika login)
      - Populer
      - Beberapa kategori unggulan
    """
    hal = HalamanRekomendasi()
    hal.tambah(produk_terbaru(df_buku, n=6))

    if username:
        hal.tambah(rekomendasi_untuk_anda(username, df_buku, df_fav, n=6))

    hal.tambah(populer_berdasarkan_favorit(df_buku, df_fav, n=6))

    for blok in produk_per_kategori(df_buku, n_per_kategori=4, max_kategori=4):
        hal.tambah(blok)

    return hal


def halaman_produk_kami(df_buku: pd.DataFrame) -> HalamanRekomendasi:
    """Semua kategori — analog /produk-kami/ Jendela Book."""
    hal = HalamanRekomendasi()
    for blok in produk_per_kategori(df_buku, n_per_kategori=8, max_kategori=20):
        hal.tambah(blok)
    return hal


def halaman_detail(
    judul: str,
    df_buku: pd.DataFrame,
    df_fav: pd.DataFrame,
) -> HalamanRekomendasi:
    """
    Struktur halaman detail produk Jendela Book:
      - Produk Terkait (KNN)
      - Seri Terkait
      - Lainnya di Kategori Ini
    """
    hal = HalamanRekomendasi()
    hal.tambah(produk_terkait(judul, df_buku, df_fav, n=6))
    hal.tambah(seri_terkait(judul, df_buku, n=6))
    hal.tambah(lainnya_di_kategori_ini(judul, df_buku, n=6))
    return hal


def halaman_rekomendasi_penuh(
    username: str,
    df_buku: pd.DataFrame,
    df_fav: pd.DataFrame,
) -> HalamanRekomendasi:
    """Halaman dedicated rekomendasi personal."""
    hal = HalamanRekomendasi()
    hal.tambah(rekomendasi_untuk_anda(username, df_buku, df_fav, n=12))
    fav_user = df_fav[df_fav["username"] == username]["judul_buku"].tolist()
    for judul in fav_user[:3]:
        hal.tambah(produk_terkait(judul, df_buku, df_fav, n=4))
    return hal


# ---------------------------------------------------------------------------
# Kompatibilitas API lama
# ---------------------------------------------------------------------------
def rekomendasi_terkait_buku(
    judul: str,
    df_buku: pd.DataFrame,
    df_fav: pd.DataFrame,
    n_hasil: int = 3,
) -> tuple[list[str], str]:
    blok = produk_terkait(judul, df_buku, df_fav, n=n_hasil)
    return blok.judul_buku, blok.metode


def cari_pustaka(
    df: pd.DataFrame,
    kata_kunci: str,
    kolom: str,
    obyek: str,
) -> pd.DataFrame:
    hasil = df.copy()
    hasil["Tipe"] = hasil["Rak"].apply(_infer_tipe)

    if obyek and obyek != "Pilih obyek":
        mapping = {
            "Buku": "buku",
            "Jurnal": "jurnal",
            "Prosiding": "jurnal",
            "TA/Skripsi/Tesis": "ta_skripsi",
        }
        tipe_filter = mapping.get(obyek)
        if tipe_filter:
            hasil = hasil[hasil["Tipe"] == tipe_filter]

    if not kata_kunci.strip():
        return hasil

    kw = kata_kunci.strip()
    kolom_map = {
        "Judul": "Judul Buku",
        "Pengarang": "Pengarang",
        "Penerbit": "Rak",
        "Subyek": "Rak",
    }
    field = kolom_map.get(kolom, "Judul Buku")
    if kolom in ("Pilih Kolom", None) or not kolom:
        mask = (
            hasil["Judul Buku"].str.contains(kw, case=False, na=False)
            | hasil["Pengarang"].str.contains(kw, case=False, na=False)
            | hasil["Rak"].str.contains(kw, case=False, na=False)
        )
    else:
        mask = hasil[field].str.contains(kw, case=False, na=False)

    return hasil[mask]


__all__ = [
    "BlokRekomendasi",
    "HalamanRekomendasi",
    "build_user_book_matrix",
    "cari_pustaka",
    "halaman_beranda",
    "halaman_detail",
    "halaman_produk_kami",
    "halaman_rekomendasi_penuh",
    "knn_user_based",
    "produk_terkait",
    "produk_terbaru",
    "rekomendasi_untuk_anda",
    "rekomendasi_terkait_buku",
]
