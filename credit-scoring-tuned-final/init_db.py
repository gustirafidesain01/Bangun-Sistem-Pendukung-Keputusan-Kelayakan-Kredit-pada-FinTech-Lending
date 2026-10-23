"""
init_db.py
----------
Membuat semua tabel database (users, pengajuan) dan akun awal.
Jalankan sekali sebelum pertama kali menjalankan aplikasi:

    python init_db.py

Pastikan MySQL (XAMPP) sudah menyala dan database 'credit_scoring'
sudah dibuat terlebih dahulu lewat phpMyAdmin (atau set USE_SQLITE=1
di file .env untuk mencoba tanpa MySQL).
"""
from app import app
from extensions import db
from models import User

with app.app_context():
    db.create_all()
    print("Tabel database berhasil dibuat: users, pengajuan")

    # --- Buat akun admin default (jika belum ada) ---
    if not User.query.filter_by(username="admin").first():
        admin = User(
            nama_lengkap="Administrator",
            username="admin",
            role="admin",
        )
        admin.set_password("admin123")
        db.session.add(admin)
        print("Akun admin dibuat -> username: admin | password: admin123")
    else:
        print("Akun admin sudah ada, dilewati.")

    # --- Buat akun analis contoh (jika belum ada) ---
    if not User.query.filter_by(username="analis1").first():
        analis = User(
            nama_lengkap="Analis Kredit Contoh",
            username="analis1",
            role="analis",
        )
        analis.set_password("analis123")
        db.session.add(analis)
        print("Akun analis dibuat  -> username: analis1 | password: analis123")
    else:
        print("Akun analis1 sudah ada, dilewati.")

    db.session.commit()
    print("\nSelesai! Silakan jalankan: python app.py")
    print("PENTING: Segera ganti password default ini setelah login pertama kali.")
