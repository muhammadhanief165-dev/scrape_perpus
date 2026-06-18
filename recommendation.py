# File kompatibilitas — semua logika ada di opac_recommendation.py
from opac_recommendation import (  # noqa: F401
    BlokRekomendasi,
    HalamanRekomendasi,
    build_user_book_matrix,
    cari_pustaka,
    halaman_beranda,
    halaman_detail,
    halaman_produk_kami,
    halaman_rekomendasi_penuh,
    knn_collaborative,
    knn_content_based,
    knn_user_based,
    populer_berdasarkan_favorit,
    produk_terbaru,
    produk_terkait,
    produk_per_kategori,
    rekomendasi_terkait_buku,
    rekomendasi_untuk_anda,
    seri_terkait,
)

__all__ = [
    "BlokRekomendasi",
    "HalamanRekomendasi",
    "cari_pustaka",
    "halaman_beranda",
    "halaman_detail",
    "halaman_produk_kami",
    "halaman_rekomendasi_penuh",
    "produk_terkait",
]
