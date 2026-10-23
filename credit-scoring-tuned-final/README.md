# Sistem Prediksi Kelayakan Kredit FinTech (Aplikasi FULL)

Aplikasi lengkap untuk skripsi **"Rancang Bangun Sistem Prediksi Kelayakan Kredit
FinTech Menggunakan Algoritma XGBoost Berbasis Web"** — sudah menggunakan **data asli**
dari Kaggle (Credit Risk Dataset), dengan autentikasi, database, dan alur kerja lengkap.

## Update Terbaru: Pipeline Model Sudah Diperbaiki (v3)

Setelah tinjauan metodologis, `train_model.py` sudah diperbaiki untuk mengatasi
beberapa isu yang bisa memengaruhi validitas hasil di Bab IV:

- **Urutan preprocessing diperbaiki** — split train-test dilakukan SEBELUM imputasi
  missing value (median dihitung hanya dari data latih), mencegah data leakage.
- **SMOTENC menggantikan SMOTE biasa** — mencegah oversampling menghasilkan nilai
  kategorikal pecahan yang tidak valid (misal loan_grade = 3.7).
- **Encoding berbeda sesuai model** — XGBoost & Random Forest pakai Label Encoding,
  Logistic Regression pakai One-Hot Encoding (lebih adil untuk model linear).
- **Fitur `loan_grade` dikeluarkan** — hasil ablation study menunjukkan penurunan
  performa sangat kecil (~1 poin persentase), dan fitur ini berpotensi sirkular
  secara konseptual karena sudah merupakan representasi penilaian risiko.

Hasil setelah perbaikan pipeline (data uji, 10 fitur tanpa loan_grade):

| Model | Akurasi | Presisi | Recall | F1-Score | ROC-AUC |
|---|---|---|---|---|---|
| **XGBoost** | 92,0% | 90,0% | 71,3% | 79,6% | 0,935 |
| Random Forest | 87,5% | 70,4% | 73,5% | 71,9% | 0,903 |
| Logistic Regression | 77,3% | 48,8% | 76,8% | 59,7% | 0,847 |

Catatan: Logistic Regression membaik signifikan dibanding versi sebelumnya (F1-Score
naik dari 57,8% ke 59,7%) — membuktikan perbaikan encoding memang berpengaruh nyata,
bukan cuma penyesuaian kosmetik.

Form input di aplikasi (Prediksi Baru, Edit Pengajuan) sudah disesuaikan — field
"Grade Pinjaman" dihapus karena tidak lagi jadi fitur model. Kolom `loan_grade` di
database tetap ada (nullable) untuk kompatibilitas data lama, tapi tidak lagi wajib
diisi atau dipakai untuk prediksi.

**Yang masih tersisa:** hyperparameter tuning XGBoost (belum dikerjakan).

## Update: Hyperparameter Tuning Selesai

`RandomizedSearchCV` (15 kombinasi parameter × 3-fold cross-validation) dijalankan
dengan SMOTENC di-nest di dalam setiap fold CV (bukan diterapkan sekali di awal),
supaya data sintetis hasil oversampling tidak "bocor" antar fold latih/validasi —
pendekatan yang lebih ketat dibanding praktik umum.

**Parameter terbaik:** `n_estimators=400, max_depth=7, learning_rate=0.15, subsample=0.9, colsample_bytree=0.9, min_child_weight=1`

**Hasil sebelum vs sesudah tuning (data uji):**

| Metrik | Sebelum Tuning | Sesudah Tuning | Perubahan |
|---|---|---|---|
| Akurasi | 92,00% | 92,45% | +0,45 poin |
| Presisi | 89,97% | 89,47% | -0,50 poin |
| Recall | 71,31% | 74,12% | +2,81 poin |
| F1-Score | 79,56% | 81,08% | +1,52 poin |
| ROC-AUC | 0,9349 | 0,9428 | +0,0079 |

Recall & F1-Score naik paling signifikan — model sekarang lebih baik mendeteksi
pemohon "Berisiko Tinggi" yang sebenarnya, yang penting karena kesalahan meloloskan
peminjam berisiko biasanya lebih mahal daripada menolak yang sebenarnya layak.

Model final (`model/xgb_model.pkl`) sekarang berupa gabungan Pipeline (SMOTENC +
XGBoost) yang sudah dilatih dengan parameter terbaik — kompatibel penuh dengan
`app.py` tanpa perlu perubahan kode (Pipeline otomatis melewati langkah SMOTENC
saat prediksi, hanya aktif saat training).

**SEMUA 6 LANGKAH PIPELINE SUDAH SELESAI.** Yang tersisa sekarang murni pengembangan
UI (sidebar collapsible) dan penulisan skripsi.

## Yang Sudah Ada di Versi Ini (v2 — Lengkap)

- ✅ Model XGBoost dilatih pakai **data asli Kaggle** (32.581 baris), bukan simulasi lagi
- ✅ Data cleaning (hapus outlier), penanganan missing value, encoding kategorikal, SMOTE
- ✅ Perbandingan XGBoost vs Random Forest vs Logistic Regression
- ✅ **Login & 2 peran pengguna**: Analis Kredit & Admin
- ✅ **Database MySQL** (via XAMPP) untuk menyimpan histori pengajuan
- ✅ Dashboard dengan **grafik** (proporsi Layak/Berisiko, pengajuan per analis)
- ✅ Form prediksi dengan **validasi input** (usia, pendapatan, dll divalidasi sebelum diproses)
- ✅ Halaman detail dengan konfirmasi keputusan analis
- ✅ **Edit pengajuan** — perbaiki data salah input, prediksi dihitung ulang otomatis
- ✅ **Batalkan pengajuan** — tandai data tidak valid, bisa diaktifkan kembali kapan saja (terpisah dari keputusan kredit)
- ✅ **Hapus pengajuan** — masuk Tempat Sampah 30 hari, bisa direstore oleh pemilik data atau Admin
- ✅ **Export Excel** (riwayat pengajuan) dan **Export PDF** (laporan evaluasi model)
- ✅ **Profil Saya** — edit nama & ganti password sendiri
- ✅ **Kelola User lengkap** — tambah, edit, nonaktifkan, dan **reset password** user lain
- ✅ **Log Aktivitas** — jejak audit semua aksi penting (khusus Admin)
- ✅ Riwayat pengajuan dengan pencarian, filter status, dan filter per analis (khusus Admin)
- ✅ Halaman error kustom (404/403/500) — bukan error mentah Flask
- ✅ Laporan & evaluasi model (khusus Admin)

Semua sudah **diuji coba end-to-end secara menyeluruh** (termasuk pengecekan hak akses
antar-role) sebelum dikirim ke kamu.

---

## Struktur Folder

```
credit-scoring-full/
├── app.py                   # Aplikasi utama Flask (semua routing)
├── config.py                # Konfigurasi koneksi database
├── extensions.py            # Inisialisasi db & login manager
├── models.py                # Model database: User, Pengajuan
├── init_db.py                # Skrip membuat tabel & akun awal
├── train_model.py            # Skrip pelatihan model (data asli Kaggle)
├── schema.sql                 # Struktur tabel SQL (opsional, untuk phpMyAdmin)
├── requirements.txt
├── .env.example                # Contoh konfigurasi (salin jadi .env)
├── data/
│   └── credit_risk_dataset.csv   # Dataset asli dari Kaggle
├── model/
│   ├── xgb_model.pkl             # Model XGBoost terlatih
│   ├── scaler.pkl
│   ├── encoders.pkl               # Encoder untuk fitur kategorikal
│   └── metrics.json               # Hasil evaluasi & feature importance
├── templates/                     # Semua halaman HTML
└── static/                        # CSS & JS
```

---

## Cara Menjalankan (Laragon / XAMPP + VS Code)

### 1. Siapkan Database MySQL

1. Nyalakan **Apache** dan **MySQL** di XAMPP/Laragon Control Panel
2. Buka `http://localhost/phpmyadmin`
3. Buat database baru dengan nama **`credit_scoring`** (klik "New", ketik nama, klik "Create")
   — tidak perlu import `schema.sql`, tabel akan dibuat otomatis di langkah berikutnya

### 2. Siapkan Environment Python

Buka folder project di VS Code, lalu buka terminal:

```bash
# Buat virtual environment (disarankan)
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux

# Install semua dependency
pip install -r requirements.txt
```

### 3. Konfigurasi Koneksi Database

Salin file `.env.example` menjadi `.env`:

```bash
copy .env.example .env       # Windows
# cp .env.example .env       # Mac/Linux
```

Buka `.env`, sesuaikan kalau perlu (default sudah cocok untuk XAMPP standar: user `root`,
tanpa password, port `3306`).

### 4. Buat Tabel & Akun Awal

```bash
python init_db.py
```

Ini akan membuat tabel `users` dan `pengajuan` di database `credit_scoring`, plus 2 akun awal:

| Role | Username | Password |
|---|---|---|
| Admin | `admin` | `admin123` |
| Analis Kredit | `analis1` | `analis123` |

**⚠️ Segera ganti password ini setelah login pertama kali** (lewat menu Kelola User untuk admin).

### 5. Jalankan Aplikasi

```bash
python app.py
```

Buka browser ke **http://127.0.0.1:5050**, lalu login pakai akun di atas.

---

## Model Machine Learning yang Digunakan

Model dilatih dari `train_model.py` menggunakan dataset **Credit Risk Dataset** dari Kaggle
(sumber: kaggle.com/datasets/laotse/credit-risk-dataset), dengan tahapan sesuai Bab 1.4 proposal:

1. **Data Cleaning** — menghapus baris dengan usia > 80 tahun / lama kerja > 60 tahun (outlier)
2. **Missing Value Handling** — mengisi nilai kosong pada `person_emp_length` dan
   `loan_int_rate` dengan median
3. **Encoding** — `person_home_ownership`, `loan_intent`, `loan_grade`,
   `cb_person_default_on_file` di-encode dengan Label Encoding
4. **SMOTE** — menyeimbangkan data latih (awalnya 78% Non-Default vs 22% Default)
5. **Pelatihan & Perbandingan** — XGBoost vs Random Forest vs Logistic Regression

Hasil evaluasi (data uji, tidak pernah dilihat model saat training):

| Model | Akurasi | Presisi | Recall | F1-Score | ROC-AUC |
|---|---|---|---|---|---|
| **XGBoost** | 92.7% | 93.4% | 71.7% | 81.1% | 0.935 |
| Random Forest | 88.0% | 71.5% | 74.6% | 73.1% | 0.908 |
| Logistic Regression | 77.4% | 48.7% | 71.0% | 57.8% | 0.826 |

XGBoost unggul di semua metrik utama — cocok jadi bahan pembahasan di Bab 4 skripsimu.

**Kalau ingin melatih ulang model** (misalnya setelah mengganti/menambah data), jalankan:
```bash
python train_model.py
```
Ini akan memperbarui file di folder `model/` secara otomatis.

---

## Alur Aplikasi

1. **Login** → sistem cek role (Analis/Admin)
2. **Dashboard** → ringkasan jumlah pengajuan, grafik proporsi Layak/Berisiko
3. **Prediksi Baru** → Analis input data calon peminjam (tervalidasi otomatis)
4. **Sistem jalankan model XGBoost** → skor kredit & faktor risiko ditampilkan
5. **Analis konfirmasi keputusan** → Disetujui / Ditolak / Menunggu, dengan catatan opsional
6. **Data tersimpan ke database** → bisa dilihat lagi lewat Riwayat Pengajuan
7. **Kalau ada salah input** → gunakan menu **Edit** (prediksi dihitung ulang otomatis)
8. **Kalau data tidak valid** → gunakan **Batalkan** (beda dari "Ditolak" — bisa diaktifkan lagi kapan saja)
9. **Kalau mau dibuang** → gunakan **Hapus** (masuk Tempat Sampah 30 hari, bisa direstore)
10. **Admin bisa lihat Laporan** → statistik agregat + evaluasi performa model, bisa export PDF
11. **Admin bisa Kelola User** → tambah/edit/nonaktifkan akun, reset password
12. **Admin bisa lihat Log Aktivitas** → audit trail semua aksi penting di sistem

## Hak Akses (Ringkasan)

| Fitur | Analis Kredit | Admin |
|---|---|---|
| Dashboard, Prediksi Baru | ✅ | ✅ |
| Edit/Batalkan/Hapus pengajuan **milik sendiri** | ✅ | ✅ |
| Edit/Batalkan/Hapus pengajuan **milik analis lain** | ❌ | ✅ |
| Restore dari Tempat Sampah **milik sendiri** | ✅ | ✅ |
| Restore dari Tempat Sampah **milik analis lain** | ❌ | ✅ |
| Lihat Riwayat **semua analis** | ❌ (cuma punya sendiri) | ✅ |
| Laporan & Evaluasi Model | ❌ | ✅ |
| Kelola User & Reset Password | ❌ | ✅ |
| Log Aktivitas | ❌ | ✅ |
| Export Excel (riwayat) | ✅ (punya sendiri) | ✅ (semua) |
| Export PDF (laporan) | ❌ | ✅ |

---

## Troubleshooting

**Error `Access denied for user 'root'@'localhost'`**
→ Cek username/password MySQL di `.env`. XAMPP default: user `root`, password kosong.
Kalau di Laragon kamu pakai password lain, sesuaikan `DB_PASSWORD` di `.env`.

**Error `Unknown database 'credit_scoring'`**
→ Kamu belum membuat database di phpMyAdmin. Ulangi langkah 1.

**Ingin coba tanpa MySQL dulu (misal MySQL belum siap)**
→ Buka `.env`, ubah `USE_SQLITE=0` menjadi `USE_SQLITE=1`, lalu jalankan ulang
`python init_db.py` dan `python app.py`. Aplikasi akan pakai file `credit_scoring.db`
lokal (SQLite) sebagai gantinya — cocok untuk uji cepat, tapi untuk versi final
tetap disarankan pakai MySQL sesuai proposal.

**Halaman blank / error 500**
→ Jalankan `python app.py` langsung dari terminal (bukan double-click), lihat pesan
error yang muncul di terminal untuk detail penyebabnya.

---

## Catatan untuk Bab Keterbatasan Penelitian (pengingat dari diskusi sebelumnya)

Jangan lupa cantumkan di proposal/skripsi bahwa dataset yang dipakai adalah dataset publik
dari Kaggle, karena akses ke data internal perusahaan FinTech dibatasi ketentuan kerahasiaan
data nasabah (OJK & UU PDP). Contoh kalimatnya sudah pernah saya berikan di diskusi kita —
tinggal disesuaikan ke bagian keterbatasan penelitian di proposal.
