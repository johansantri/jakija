import random
from faker import Faker
from django.utils import timezone
from authentication.models import CustomUser, Universiti  # ganti 'yourapp' sesuai app-mu

fake = Faker()

# Ambil semua universitas yang ada
universities = list(Universiti.objects.all())

education_choices = [choice[0] for choice in CustomUser.EDUCATION_CHOICES]
gender_choices = [choice[0] for choice in CustomUser.GENDER_CHOICES]
country_choices = [choice[0] for choice in CustomUser.choice_country]

users_to_create = []

for _ in range(50000):
    username = fake.user_name() + str(fake.random_number(digits=5))
    email = fake.unique.email()
    birth_date = fake.date_of_birth(minimum_age=18, maximum_age=60)
    university = random.choice(universities) if universities else None
    user = CustomUser(
        username=username,
        email=email,
        phone=fake.phone_number(),
        country=random.choice(country_choices),
        birth=birth_date,
        address=fake.address(),
        hobby=fake.word(),
        education=random.choice(education_choices),
        gender=random.choice(gender_choices),
        university=university,
        is_learner=True,
        date_joined=timezone.now(),
    )
    users_to_create.append(user)

# Bulk create untuk performance
CustomUser.objects.bulk_create(users_to_create, batch_size=1000)
print("50,000 dummy users created successfully!")
