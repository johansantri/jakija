# LMS JakIja

JakIja is a Learning Management System (LMS) built with Python and Django, designed for multi‑vendor use. With JakIja, course providers can create, manage, and sell courses independently — suitable for educational institutions, companies, and training teams.

## Overview
- Original repo: https://github.com/johansantri/mysite  
- Goal: lightweight, team‑oriented online learning platform

<details>
<summary>Key Features (click to expand)</summary>

### **User Management**
- **Secure Login & Logout** – Sistem autentikasi aman untuk semua pengguna.  
- **Role-based Access** – Admin, guru, dan siswa memiliki hak akses berbeda.  
- **Profile Management** – Edit profil, upload foto, dan kelola preferensi.  
- **Password Recovery** – Reset password melalui email.  
- **Two-factor Authentication (2FA)** – Keamanan tambahan untuk login.  

### **Course Management**
- **Create, Edit, Delete Courses** – Kelola kursus dan modul dengan mudah.  
- **Upload Materials** – Mendukung PDF, video, audio, gambar, dan dokumen lainnya.  
- **Course Categories & Tags** – Organisasi kursus berdasarkan topik dan kata kunci.  
- **Course Scheduling** – Jadwal kelas, sesi live, atau webinar.  
- **Course Prerequisites** – Atur syarat agar siswa bisa mengikuti kursus tertentu.  

### **Assessment & Progress**
- **Quizzes & Assignments** – Berbagai tipe soal: pilihan ganda, essay, coding, dll.  
- **Automatic Grading** – Penilaian otomatis untuk soal objektif.  
- **Manual Grading** – Guru bisa menilai tugas/essay secara manual.  
- **Progress Tracking** – Pantau progres siswa secara real-time.  
- **Completion Certificates & Badges** – Sertifikat dan badge sebagai reward.  
- **Gradebook** – Rekap nilai per siswa dan kursus.  

### **Communication & Collaboration**
- **Announcements** – Informasi penting untuk siswa langsung terlihat.  
- **Discussion Forums / Boards** – Forum diskusi per kelas atau kursus.  
- **Direct Messaging / Chat** – Pesan antar guru dan siswa.  
- **Group Projects** – Fitur kerja kelompok dan kolaborasi antar siswa.  

### **Notifications & Alerts**
- **Email Notifications** – Untuk tugas, kuis, pengumuman, dan pesan.  
- **Push Notifications** – Notifikasi real-time di aplikasi mobile/web.  
- **Reminders & Deadlines** – Pengingat otomatis untuk tugas dan ujian.  

### **Analytics & Reporting**
- **Course Analytics** – Statistik kehadiran, progress, dan engagement siswa.  
- **User Reports** – Laporan performa siswa, aktivitas guru, dan interaksi.  
- **Export Data** – Ekspor data ke CSV, Excel, atau PDF.  
- **Custom Reports** – Buat laporan sesuai kebutuhan admin atau guru.  

### **Content & Multimedia**
- **Video & Audio Streaming** – Integrasi untuk video pembelajaran.  
- **Interactive Content** – Konten interaktif seperti simulasi dan kuis inline.  
- **Document Versioning** – Versi terbaru materi selalu tersedia.  

### **Integration & Extensibility**
- **Third-party Integration** – Payment gateway, Zoom, Google Drive, dsb.  
- **API Access** – Untuk integrasi dengan sistem lain.  
- **Plugin / Module Support** – Tambahkan fitur tambahan tanpa mengubah inti sistem.  

### **Accessibility & UX**
- **Responsive Design** – Optimal untuk desktop, tablet, dan mobile.  
- **Multi-language Support** – Dukungan berbagai bahasa.  
- **Dark Mode / Light Mode** – Pilihan tampilan sesuai preferensi.  
- **Keyboard Navigation & Screen Reader Support** – Aksesibilitas bagi penyandang disabilitas.  

### **Security & Compliance**
- **Data Encryption** – Semua data sensitif terenkripsi.  
- **Role-based Permissions** – Kontrol ketat untuk setiap level pengguna.  
- **GDPR / Local Compliance** – Sesuai regulasi perlindungan data.  
- **Audit Logs** – Rekam semua aktivitas penting pengguna.  

### **Gamification & Engagement**
- **Points & Badges** – Motivasi siswa melalui reward sistem.  
- **Leaderboard** – Kompetisi sehat antar siswa berdasarkan progress.  
- **Achievement Unlocks** – Fitur gamifikasi untuk pencapaian tertentu.  

### **Additional Features**
- **Offline Access** – Materi bisa diunduh untuk belajar offline (opsional).  
- **Search & Filter** – Cari kursus, materi, atau pengguna dengan mudah.  
- **Customizable Themes** – Kustomisasi tampilan LMS sesuai branding.  
- **Backup & Restore** – Sistem backup otomatis untuk keamanan data.  

</details>


## Additional features
- Payment gateway support: Tripay  
- Micro‑credentials / professional certificate support

## Requirements
- Python 3.8+ (recommended)  
- Django 5.1

## Quick install (Linux)
1. git clone https://github.com/johansantri/mysite.git  
2. cd mysite  
3. python3 -m venv .venv  
4. source .venv/bin/activate  
5. python3 -m pip install -r requirements.txt  
6. python manage.py makemigrations  
7. python manage.py migrate  
8. python manage.py createsuperuser  
9. python manage.py runserver

## Demo / Video
 
[![MYSITE demo](https://img.youtube.com/vi/UXxBFmejhe8/maxresdefault.jpg)](https://www.youtube.com/watch?v=UXxBFmejhe8)

## Migration notes
If you encounter issues with old migrations, back up and remove non‑essential migration files for the affected apps before running `makemigrations`.

## License
This project is licensed under the MIT License — see `LICENSE` for details.

## Contributing
Pull requests are welcome. Please include a description of changes and tests when applicable. Consider adding `CONTRIBUTING.md` and `CODE_OF_CONDUCT.md`.

## Attribution (must appear on the official site footer)
Creator: Johan Santri  
The official site must display this attribution in the footer (example: `templates/base.html`).

## Contact
Repository: https://github.com/johansantri/mysite

## Demo accounts
- Superuser: admin@admin.com | admin  
- Partner: partner@partner.com | partner  
- Instructor: instructor@instructor.com | instructor  
- Learner: learn@learn.com | learn  
- Subscription: sub@sub.com | sub  
- Curation: curation@curation.com | curation  
- Finances: fin@fin.com | fin