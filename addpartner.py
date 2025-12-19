from courses.models import Partner
from authentication.models import CustomUser,Universiti
from django.utils import timezone
from faker import Faker
import random

fake = Faker()

# Ambil semua user dan universitas
users = CustomUser.objects.all()
universities = Universiti.objects.all()

for user in users:
    # Cek supaya tidak bikin duplicate Partner untuk user yang sama
    if not hasattr(user, 'partner_user'):
        university = random.choice(universities)
        partner = Partner.objects.create(
            user=user,
            author=user,
    
            name=university,
            phone=fake.phone_number(),
            address=fake.address(),
            description=fake.text(max_nb_chars=200),
            tax=random.randint(0, 20),
            iceiprice=random.randint(0, 30),
            account_number=fake.bban(),
            account_holder_name=fake.name(),
            bank_name=fake.company(),
            balance=random.randint(0, 1000000),
            business_type=random.choice([choice[0] for choice in Partner.BUSINESS_TYPE_CHOICES]),
            payment_method=random.choice([choice[0] for choice in Partner.PAYMENT_METHOD_CHOICES]),
            currency='IDR',
            is_active=True,
            is_verified=random.choice([True, False]),
            verified_at=timezone.now() if random.choice([True, False]) else None,
            partner_code=fake.unique.bothify(text='PARTNER-####'),
            finance_note=fake.sentence(),
            agreed_to_terms=True,
            status=random.choice([choice[0] for choice in Partner.STATUS_CHOICES])
        )
        print(f"Partner created: {partner}")
