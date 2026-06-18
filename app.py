import html
import os

import pandas as pd
import streamlit as st

from opac_recommendation import (
    BlokRekomendasi,
    HalamanRekomendasi,
    cari_pustaka,
    halaman_beranda,
    halaman_detail,
    halaman_produk_kami,
    halaman_rekomendasi_penuh,
    produk_terkait,
)
from scrape_perpus import scrape_opac

st.set_page_config(
    page_title="OPAC :: Pencarian Pustaka",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

USER_FILE = "users.csv"
FAV_FILE = "favorites.csv"
CSV_BUKU = "daftar_buku_amikom.csv"


def load_css(file_name: str) -> None:
    with open(file_name, encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


load_css("style.css")

# Efek tekan pada kartu buku saat diklik (border/konten)
st.markdown(
    """
    <script>
    (function () {
        if (window.__opacCardPressFx) return;
        window.__opacCardPressFx = true;

        function kartu(el) {
            return el && el.closest('[data-testid="stVerticalBlockBorderWrapper"]');
        }

        document.body.addEventListener("mousedown", function (e) {
            var c = kartu(e.target);
            if (c) c.classList.add("card-ditekan");
        }, true);

        document.body.addEventListener("mouseup", function () {
            document.querySelectorAll(".card-ditekan").forEach(function (c) {
                c.classList.remove("card-ditekan");
                c.classList.add("card-kilat");
                setTimeout(function () { c.classList.remove("card-kilat"); }, 450);
            });
        }, true);

        /* Klik di mana saja pada border/kartu -> buka detail buku */
        document.body.addEventListener("click", function (e) {
            if (e.target.closest("button, a, input, textarea, select")) return;
            var card = e.target.closest('[data-testid="stVerticalBlockBorderWrapper"]');
            if (!card) return;
            var marker = card.querySelector("[data-card-key]");
            if (!marker) return;
            var key = marker.getAttribute("data-card-key");
            var u = new URL(window.location.href);
            u.searchParams.set("kartu", key);
            window.location.href = u.toString();
        }, true);
    })();
    </script>
    """,
    unsafe_allow_html=True,
)


def load_users() -> pd.DataFrame:
    if not os.path.exists(USER_FILE):
        pd.DataFrame({"username": ["admin"], "password": ["12345"]}).to_csv(
            USER_FILE, index=False
        )
    return pd.read_csv(USER_FILE, dtype=str)


def register_user(new_username: str, new_password: str) -> bool:
    df_users = load_users()
    if new_username in df_users["username"].values:
        return False
    baru = pd.DataFrame(
        {"username": [str(new_username)], "password": [str(new_password)]}
    )
    pd.concat([df_users, baru], ignore_index=True).to_csv(USER_FILE, index=False)
    return True


def load_favorites() -> pd.DataFrame:
    if not os.path.exists(FAV_FILE):
        pd.DataFrame({"username": [], "judul_buku": []}).to_csv(FAV_FILE, index=False)
    return pd.read_csv(FAV_FILE)


def add_favorite(username: str, judul_buku: str) -> bool:
    df_fav = load_favorites()
    sudah = ((df_fav["username"] == username) & (df_fav["judul_buku"] == judul_buku)).any()
    if sudah:
        return False
    baru = pd.DataFrame({"username": [username], "judul_buku": [judul_buku]})
    pd.concat([df_fav, baru], ignore_index=True).to_csv(FAV_FILE, index=False)
    return True


def remove_favorite(username: str, judul_buku: str) -> None:
    df_fav = load_favorites()
    df_fav = df_fav[~((df_fav["username"] == username) & (df_fav["judul_buku"] == judul_buku))]
    df_fav.to_csv(FAV_FILE, index=False)


if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "auth_mode" not in st.session_state:
    st.session_state["auth_mode"] = "login"
if "halaman" not in st.session_state:
    st.session_state["halaman"] = "beranda"
if "detail_judul" not in st.session_state:
    st.session_state["detail_judul"] = None
if "dialog_terbuka" not in st.session_state:
    st.session_state["dialog_terbuka"] = False
if "kartu_judul_map" not in st.session_state:
    st.session_state["kartu_judul_map"] = {}


@st.cache_data
def load_buku() -> pd.DataFrame:
    df = pd.read_csv(CSV_BUKU)
    for col in ("Judul Buku", "Pengarang", "Rak"):
        df[col] = df[col].fillna("")
    df["Konten"] = df["Judul Buku"] + " " + df["Pengarang"] + " " + df["Rak"]
    return df


df = load_buku()
df_fav = load_favorites()


# ==========================================
# SIDEBAR
# ==========================================
with st.sidebar:
    st.markdown(
        '<p class="sidebar-brand">Amikom<br><span>Resource Centre</span></p>',
        unsafe_allow_html=True,
    )

    if not st.session_state["logged_in"]:
        if st.session_state["auth_mode"] == "login":
            st.subheader("Login")
            login_user = st.text_input("Username", key="log_user")
            login_pass = st.text_input("Password", type="password", key="log_pass")
            if st.button("Masuk", use_container_width=True, type="primary"):
                df_users = load_users()
                cek = df_users[
                    (df_users["username"] == login_user)
                    & (df_users["password"] == login_pass)
                ]
                if not cek.empty:
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = login_user
                    st.rerun()
                else:
                    st.error("Username atau password salah.")
            st.divider()
            if st.button("Buat akun baru", use_container_width=True):
                st.session_state["auth_mode"] = "register"
                st.rerun()
        else:
            st.subheader("Daftar akun")
            reg_user = st.text_input("Username", key="reg_user")
            reg_pass = st.text_input("Password", type="password", key="reg_pass")
            if st.button("Daftar", use_container_width=True, type="primary"):
                if not reg_user or not reg_pass:
                    st.warning("Username dan password wajib diisi.")
                elif register_user(reg_user, reg_pass):
                    st.success("Akun berhasil dibuat. Silakan login.")
                    st.session_state["auth_mode"] = "login"
                    st.rerun()
                else:
                    st.error("Username sudah terdaftar.")
            st.divider()
            if st.button("Kembali ke login", use_container_width=True):
                st.session_state["auth_mode"] = "login"
                st.rerun()
    else:
        st.success(f"Halo, **{st.session_state['username']}**")
        if st.button("Logout", use_container_width=True):
            st.session_state["logged_in"] = False
            st.session_state["auth_mode"] = "login"
            st.rerun()

    st.divider()
    st.caption("Navigasi")
    nav_items = [
        ("beranda", "Beranda"),
        ("produk", "Produk Kami"),
        ("ta", "TA/Skripsi/Tesis"),
    ]
    if st.session_state["logged_in"]:
        nav_items.append(("rekomendasi", "Rekomendasi Untuk Anda"))

    for key, label in nav_items:
        if st.button(label, use_container_width=True, key=f"nav_{key}"):
            st.session_state["halaman"] = key
            st.rerun()

    st.divider()
    st.caption("Data OPAC")
    if st.button("Scrape 200 buku", use_container_width=True):
        with st.spinner("Scraping opac.amikom.ac.id..."):
            jumlah = scrape_opac(target=200, timpa_file=True)
        load_buku.clear()
        st.sidebar.success(f"{jumlah} buku tersimpan.")
        st.rerun()
    if st.button("Segarkan data", use_container_width=True):
        load_buku.clear()
        st.rerun()


# ==========================================
# KOMPONEN UI (struktur Jendela Book)
# ==========================================
def badge_status(status: str) -> str:
    if str(status).upper() == "TERSEDIA":
        return '<span class="badge tersedia">TERSEDIA</span>'
    return '<span class="badge kosong">KOSONG</span>'


def tampilkan_section_jendela(blos: BlokRekomendasi, prefix_key: str) -> None:
    """Satu section rekomendasi — judul + grid produk (seperti Jendela Book)."""
    desc_html = (
        f'<p class="section-desc">{blos.deskripsi}</p>' if blos.deskripsi.strip() else ""
    )
    st.markdown(
        f'<div class="section-jendela"><h2 class="section-title">{blos.judul_section}</h2>'
        f'{desc_html}</div>',
        unsafe_allow_html=True,
    )

    df_section = df[df["Judul Buku"].isin(blos.judul_buku)]
    if df_section.empty:
        return

    # Urutkan sesuai urutan rekomendasi
    urutan = {j: i for i, j in enumerate(blos.judul_buku)}
    df_section = df_section.copy()
    df_section["_urut"] = df_section["Judul Buku"].map(urutan)
    df_section = df_section.sort_values("_urut")

    cols = st.columns(min(4, len(df_section)))
    for index, (_, row) in enumerate(df_section.iterrows()):
        with cols[index % len(cols)]:
            judul = row["Judul Buku"]
            card_key = f"{prefix_key}_{blos.id}_{index}"
            st.session_state["kartu_judul_map"][card_key] = judul

            with st.container(border=True):
                st.markdown(
                    f'<div class="kartu-buku-marker" data-card-key="{html.escape(card_key)}"></div>',
                    unsafe_allow_html=True,
                )
                st.image(
                    "https://placehold.co/300x400/4A148C/ffffff?text=📚",
                    use_container_width=True,
                )
                judul_pendek = judul[:42] + "..." if len(judul) > 45 else judul
                st.markdown(f"**{judul_pendek}**")
                st.markdown(
                    f'<small class="card-pengarang">{row["Pengarang"][:28]}</small>',
                    unsafe_allow_html=True,
                )
                st.markdown(badge_status(row.get("Status", "")), unsafe_allow_html=True)
                st.button("Detail buku", key=f"detail_{card_key}", use_container_width=True, on_click=_pilih_buku_detail, args=(judul,))
    st.divider()


def tampilkan_halaman_rekomendasi(hal: HalamanRekomendasi, prefix: str) -> None:
    """Render semua blok rekomendasi satu halaman."""
    for i, blok in enumerate(hal.blok):
        tampilkan_section_jendela(blok, f"{prefix}_{i}")


def _tutup_dialog_detail() -> None:
    st.session_state["dialog_terbuka"] = False
    st.session_state["detail_judul"] = None


def _pilih_buku_detail(judul: str) -> None:
    st.session_state["detail_judul"] = judul
    st.session_state["dialog_terbuka"] = True


def buka_detail(baris_data: pd.Series) -> None:
    """Buka dialog detail buku."""
    _pilih_buku_detail(baris_data["Judul Buku"])
    st.rerun()


@st.dialog("Detail Pustaka", on_dismiss=_tutup_dialog_detail)
def pop_up_detail() -> None:
    judul = st.session_state.get("detail_judul")
    if not judul:
        return

    baris_data = df[df["Judul Buku"] == judul]
    if baris_data.empty:
        st.warning("Data buku tidak ditemukan.")
        return
    baris_data = baris_data.iloc[0]
    key_suffix = str(abs(hash(judul)))

    col1, col2 = st.columns([1, 2])
    with col1:
        st.image(
            "https://placehold.co/300x450/4A148C/ffffff?text=📚",
            use_container_width=True,
        )
    with col2:
        st.subheader(judul)
        st.markdown(f"**Pengarang:** {baris_data['Pengarang']}")
        st.markdown(f"**Lokasi / Rak:** {baris_data['Rak']}")
        st.markdown(
            f"**Eksemplar:** {baris_data.get('Jumlah Eksemplar', '-')} — "
            f"{baris_data.get('Status', '-')}"
        )

        if st.session_state["logged_in"]:
            user = st.session_state["username"]
            sudah_fav = (
                (df_fav["username"] == user) & (df_fav["judul_buku"] == judul)
            ).any()
            if sudah_fav:
                if st.button("Hapus dari favorit", key=f"popup_unfav_{key_suffix}"):
                    remove_favorite(user, judul)
                    st.rerun()
            elif st.button("Tambah ke favorit", type="primary", key=f"popup_fav_{key_suffix}"):
                if add_favorite(user, judul):
                    st.success("Disimpan ke favorit.")
                    st.rerun()
        else:
            st.info("Login untuk favorit & rekomendasi personal.")


def navbar_utama() -> None:
    """Navbar horizontal — selalu tampil meski sidebar ditutup."""
    nav_items = [
        ("beranda", "Beranda"),
        ("produk", "Produk Kami"),
        ("ta", "TA/Skripsi/Tesis"),
    ]
    if st.session_state["logged_in"]:
        nav_items.append(("rekomendasi", "Rekomendasi Untuk Anda"))

    st.markdown('<div class="navbar-top">', unsafe_allow_html=True)
    cols = st.columns(len(nav_items))
    halaman_aktif = st.session_state.get("halaman", "beranda")
    for col, (key, label) in zip(cols, nav_items):
        with col:
            tipe = "primary" if halaman_aktif == key else "secondary"
            if st.button(label, key=f"topnav_{key}", use_container_width=True, type=tipe):
                st.session_state["halaman"] = key
                st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


def header_opac() -> None:
    st.markdown(
        """
        <div class="header-amikom">
            <div class="logo-wrap">
                <span class="logo-text">Amikom</span>
                <span class="logo-sub">Resource Centre</span>
            </div>
            <h1>PENCARIAN PUSTAKA</h1>
            <p class="subtitle">Pilih obyek dan kolom sebelum memasukan kata kunci</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def form_pencarian() -> tuple[str, str, str, bool]:
    col_kosong1, col_form, col_kosong2 = st.columns([1, 2, 1])
    with col_form:
        obyek = st.selectbox(
            "Obyek",
            ["Pilih obyek", "Buku", "Jurnal", "Prosiding", "TA/Skripsi/Tesis"],
        )
        kolom = st.selectbox(
            "Kolom",
            ["Pilih Kolom", "Judul", "Pengarang", "Penerbit", "Subyek"],
        )
        kata_kunci = st.text_input("Kata kunci", placeholder="Masukkan kata kunci...")
        btn_cari = st.button("Pencarian", type="primary", use_container_width=True)
    return obyek, kolom, kata_kunci, btn_cari


# ==========================================
# HALAMAN UTAMA
# ==========================================
st.session_state["kartu_judul_map"] = {}

navbar_utama()
header_opac()
halaman = st.session_state.get("halaman", "beranda")
user_login = st.session_state["username"] if st.session_state["logged_in"] else None

if halaman == "produk":
    st.markdown("## Produk Kami")
    st.caption("Koleksi pustaka per kategori — struktur seperti jendelabook.com/produk-kami/")
    tampilkan_halaman_rekomendasi(halaman_produk_kami(df), "produk")

elif halaman == "ta":
    hasil_ta = cari_pustaka(df, "", "Judul", "TA/Skripsi/Tesis")
    st.subheader(f"TA/Skripsi/Tesis ({len(hasil_ta)} item)")
    hal = HalamanRekomendasi()
    hal.tambah(
        BlokRekomendasi(
            id="ta",
            judul_section="Koleksi TA/Skripsi/Tesis",
            deskripsi="Karya akhir mahasiswa.",
            judul_buku=hasil_ta["Judul Buku"].head(12).tolist(),
            metode="kategori",
        )
    )
    tampilkan_halaman_rekomendasi(hal, "ta")

elif halaman == "rekomendasi":
    if not st.session_state["logged_in"]:
        st.warning("Login untuk melihat **Rekomendasi Untuk Anda**.")
    else:
        user = st.session_state["username"]
        fav_user = df_fav[df_fav["username"] == user]
        if fav_user.empty:
            st.info("Tambahkan buku ke favorit untuk melihat rekomendasi.")
        else:
            tampilkan_halaman_rekomendasi(
                halaman_rekomendasi_penuh(user, df, load_favorites()),
                "rek_penuh",
            )

else:
    obyek, kolom, kata_kunci, btn_cari = form_pencarian()

    if btn_cari:
        if obyek == "Pilih obyek":
            st.warning("Pilih obyek terlebih dahulu.")
        elif not kata_kunci.strip():
            st.warning("Masukkan kata kunci.")
        else:
            hasil = cari_pustaka(df, kata_kunci, kolom, obyek)
            st.subheader(f"Hasil: '{kata_kunci}' ({len(hasil)} item)")
            if hasil.empty:
                st.warning("Tidak ditemukan.")
            else:
                blok_hasil = BlokRekomendasi(
                    id="hasil_cari",
                    judul_section="Hasil Pencarian",
                    deskripsi="",
                    judul_buku=hasil["Judul Buku"].head(12).tolist(),
                    metode="pencarian",
                )
                tampilkan_section_jendela(blok_hasil, "search")

                # Produk terkait buku pertama (seperti related products)
                buku_teratas = hasil.iloc[0]["Judul Buku"]
                blok_terkait = produk_terkait(
                    buku_teratas, df, load_favorites(), n=6
                )
                if blok_terkait.judul_buku:
                    tampilkan_section_jendela(blok_terkait, "search_terkait")
    else:
        # Beranda — struktur Jendela Book
        hal = halaman_beranda(df, load_favorites(), username=user_login)
        tampilkan_halaman_rekomendasi(hal, "beranda")

# Klik pada border/kartu buku -> buka detail
if st.query_params.get("kartu"):
    card_key = st.query_params.get("kartu")
    judul_klik = st.session_state.get("kartu_judul_map", {}).get(card_key)
    if judul_klik:
        _pilih_buku_detail(judul_klik)
    st.query_params.clear()
    st.rerun()

# Buka ulang dialog setelah klik buku terkait (agar langsung tampil detail baru)
if st.session_state.get("dialog_terbuka") and st.session_state.get("detail_judul"):
    pop_up_detail()
