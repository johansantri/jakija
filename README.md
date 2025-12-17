# LMS JakIja

JakIja is a Learning Management System (LMS) built with Python and Django, designed for multi‑vendor use. With JakIja, course providers can create, manage, and sell courses independently — suitable for educational institutions, companies, and training teams.

## Overview
- Original repo: https://github.com/johansantri/mysite  
- Goal: lightweight, team‑oriented online learning platform

## Key Features
<details>
<summary> (click to expand)</summary>

### **User Management**
- **Secure Login & Logout** – Sistem autentikasi aman untuk semua pengguna.  
- **Role-based Access** – Admin, mitra, instruktur dan peserta memiliki hak akses berbeda.  
- **Profile Management** – Edit profil, upload foto, dan kelola preferensi.  
- **Password Recovery** – Reset password melalui email.  
- **Two-factor Authentication (2FA)** – Keamanan tambahan untuk login.  

### **Course Management**
- **Create, Edit, Delete Courses** – Kelola kursus dan modul dengan mudah.  
- **Upload Materials** – Mendukung PDF, video, audio, gambar, dan dokumen lainnya.  
- **Course Categories & Tags** – Organisasi kursus berdasarkan topik dan kata kunci.  
- **Course Scheduling** – lengkap dengan detailnya, kapan mulai kelas kapan dibuka kelas sampai berakhir  
- **Course Prerequisites** – Atur syarat peserta bisa mengikuti kursus tertentu.  

### **Assessment & Progress**
- **Quizzes & Assignments** – Berbagai tipe soal: pilihan ganda, esay atau tugas antar peserta, video quiz interaktif, lti jika ada dari external lms.  
- **Automatic Grading** – Penilaian otomatis untuk semua soal.   
- **Progress Tracking** – Pantau progres peserta secara real-time.  
- **Completion Certificates & Badges** – Sertifikat dan badge sebagai reward.  
- **Gradebook** – Rekap nilai per peserta dan kursus.  

### **Communication & Collaboration**
- **Announcements** – Informasi penting untuk peserta langsung terlihat.  
- **Discussion Forums / Boards** – Forum diskusi per materi atau kursus.  
- **Direct Messaging / Chat** – Pesan antar guru dan peserta.  


### **Notifications & Alerts**
- **Email Notifications** – Untuk tugas, kuis, pengumuman, dan pesan.    
- **Reminders & Deadlines** – Pengingat otomatis untuk tugas dan ujian.  

### **Analytics & Reporting**
- **Course Analytics** – Statistik progress, dan engagement peserta.  
- **User Reports** – Laporan performa peserta, aktivitas instruktur, dan interaksi.  
- **Export Data** – Ekspor data ke CSV, Excel.  
- **Custom Reports** – Buat laporan sesuai kebutuhan admin, mitra dan instruktur.  

### **Content & Multimedia**
- **Video & Audio Streaming** – Integrasi untuk video pembelajaran.  
- **Interactive Content** – Konten interaktif seperti simulasi dan kuis inline.  
- **Document Versioning** – Versi terbaru materi selalu tersedia.  

### **Integration & Extensibility**
- **Third-party Integration** – Payment gateway seperti tripay tersedia  
- **API Access** – Untuk integrasi dengan sistem lain.  


### **Accessibility & UX**
- **Responsive Design** – Optimal untuk desktop, tablet, dan mobile.    
- **Light Mode** – tampilan yang lembut.  


### **Security & Compliance**
- **Data Encryption** – Semua data sensitif terenkripsi.  
- **Role-based Permissions** – Kontrol ketat untuk setiap level pengguna.  
- **GDPR / Local Compliance** – Sesuai regulasi perlindungan data.  
- **Audit Logs** – Rekam semua aktivitas penting pengguna.  

### **Gamification & Engagement**
- **Points & Badges** – Motivasi peserta melalui reward sistem.  
- **Leaderboard** – Kompetisi sehat antar peserta berdasarkan progress.  
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