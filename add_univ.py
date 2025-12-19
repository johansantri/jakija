from courses.models import Universiti
from faker import Faker
from django.utils.text import slugify

fake = Faker()
universities = []

for i in range(1000):
    name = fake.company() + " University"
    slug = slugify(name) + f"-{i}"   # pastikan unik
    initials = ''.join([word[0].upper() for word in name.split() if word])
    kode = initials + 'x'
    location = fake.city()
    
    universities.append(Universiti(
        name=name,
        slug=slug,
        kode=kode,
        location=location
    ))

# Bulk insert ke database
Universiti.objects.bulk_create(universities)

print("✅ 1000 Universiti dummy berhasil dibuat tanpa error!")
