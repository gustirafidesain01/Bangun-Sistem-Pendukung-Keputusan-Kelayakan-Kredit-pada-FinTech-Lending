-- =========================================================
-- schema.sql
-- Struktur database untuk Sistem Prediksi Kelayakan Kredit FinTech
--
-- CARA PAKAI (opsional -- alternatif dari `python init_db.py`):
-- 1. Buka phpMyAdmin (http://localhost/phpmyadmin)
-- 2. Buat database baru bernama "credit_scoring"
-- 3. Buka tab "Import", pilih file ini, klik "Go"
--
-- Catatan: kalau kamu sudah menjalankan `python init_db.py`,
-- TIDAK PERLU menjalankan file ini lagi -- tabel sudah otomatis dibuat.
-- =========================================================

CREATE DATABASE IF NOT EXISTS credit_scoring
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE credit_scoring;

-- ---------------------------------------------------------
-- Tabel: users
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nama_lengkap VARCHAR(150) NOT NULL,
    username VARCHAR(80) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'analis',   -- 'analis' atau 'admin'
    aktif BOOLEAN DEFAULT TRUE,
    dibuat_pada DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- ---------------------------------------------------------
-- Tabel: pengajuan
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS pengajuan (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nama_pemohon VARCHAR(150) NOT NULL,

    -- Data pemohon
    person_age INT NOT NULL,
    person_income FLOAT NOT NULL,
    person_home_ownership VARCHAR(20) NOT NULL,
    person_emp_length FLOAT NOT NULL,
    loan_intent VARCHAR(30) NOT NULL,
    loan_grade VARCHAR(5) NOT NULL,
    loan_amnt FLOAT NOT NULL,
    loan_int_rate FLOAT NOT NULL,
    loan_percent_income FLOAT NOT NULL,
    cb_person_default_on_file VARCHAR(3) NOT NULL,
    cb_person_cred_hist_length INT NOT NULL,

    -- Hasil prediksi model
    skor_kredit INT NOT NULL,
    probabilitas_default FLOAT NOT NULL,
    rekomendasi_sistem VARCHAR(20) NOT NULL,
    faktor_risiko_json TEXT,

    -- Keputusan analis
    keputusan_analis VARCHAR(20) DEFAULT 'Menunggu',
    catatan_analis TEXT,

    dibuat_oleh INT NOT NULL,
    dibuat_pada DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (dibuat_oleh) REFERENCES users(id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------
-- Akun awal (password di-hash oleh Werkzeug, bukan plain text)
-- Login: admin / admin123  dan  analis1 / analis123
-- PENTING: baris di bawah ini TIDAK otomatis berfungsi kalau di-import
-- manual, karena hash password perlu digenerate oleh Python/Werkzeug.
-- Gunakan `python init_db.py` untuk membuat akun awal secara otomatis
-- dan aman. Bagian ini hanya sebagai referensi struktur data.
-- ---------------------------------------------------------
