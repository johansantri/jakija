# authentication/models.py
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _
from django.db.models.signals import post_save
from django.utils.text import slugify

class Universiti(models.Model):
    name = models.CharField(max_length=200, blank=True, null=True)
    slug = models.SlugField(unique=True)
    location = models.CharField(max_length=100, blank=True, null=True)
    kode = models.CharField(max_length=10, blank=True)

    def save(self, *args, **kwargs):
        if self.name:
            # Set slug otomatis dari name (contoh: "Universitas Indonesia" -> "universitas-indonesia")
            if not self.slug:
                self.slug = slugify(self.name)

            # Set kode otomatis (ambil inisial + 'x')
            if not self.kode:
                initials = ''.join([word[0].upper() for word in self.name.split() if word])
                self.kode = initials + 'x'

        super().save(*args, **kwargs)

    def __str__(self):
        return self.name or ""





class CustomUser(AbstractUser):
    EDUCATION_CHOICES = [
        ('basic', 'Basic'),
        ('secondary', 'Secondary'),
        ('higher', 'Higher'),
        ('diploma', 'Diploma'),
        ('bachelor', "Bachelor's"),
        ('master', 'Master'),
        ('doctorate', 'Doctorate'),
    ]

    GENDER_CHOICES = [
        ('male', 'Male'),
        ('female', 'Female'),
    ]

    choice_country = [
        ('af', 'Afganistan'),
        ('al', 'Albania'),
        ('dz', 'Aljazair'),
        ('ad', 'Andorra'),
        ('ao', 'Angola'),
        ('ar', 'Argentina'),
        ('am', 'Armenia'),
        ('au', 'Australia'),
        ('at', 'Austria'),
        ('az', 'Azerbaijan'),
        ('bs', 'Bahama'),
        ('bh', 'Bahrain'),
        ('bd', 'Bangladesh'),
        ('bb', 'Barbados'),
        ('by', 'Belarusia'),
        ('be', 'Belgia'),
        ('bz', 'Belize'),
        ('bj', 'Benin'),
        ('bt', 'Bhutan'),
        ('bo', 'Bolivia'),
        ('ba', 'Bosnia dan Herzegovina'),
        ('bw', 'Botswana'),
        ('br', 'Brasil'),
        ('bn', 'Brunei'),
        ('bg', 'Bulgaria'),
        ('bf', 'Burkina Faso'),
        ('bi', 'Burundi'),
        ('kh', 'Kamboja'),
        ('cm', 'Kamerun'),
        ('ca', 'Kanada'),
        ('cv', 'Cape Verde'),
        ('cf', 'Republik Afrika Tengah'),
        ('td', 'Chad'),
        ('cl', 'Cile'),
        ('cn', 'Cina'),
        ('co', 'Kolombia'),
        ('km', 'Komoro'),
        ('cd', 'Republik Demokratik Kongo'),
        ('cg', 'Kongo'),
        ('cr', 'Kosta Rika'),
        ('hr', 'Kroasia'),
        ('cu', 'Kuba'),
        ('cy', 'Siprus'),
        ('cz', 'Ceko'),
        ('ci', 'Pantai Gading'),
        ('dk', 'Denmark'),
        ('dj', 'Djibouti'),
        ('dm', 'Dominika'),
        ('do', 'Republik Dominika'),
        ('ec', 'Ekuador'),
        ('eg', 'Mesir'),
        ('sv', 'El Salvador'),
        ('gq', 'Guinea Khatulistiwa'),
        ('er', 'Eritrea'),
        ('ee', 'Estonia'),
        ('et', 'Etiopia'),
        ('fj', 'Fiji'),
        ('fi', 'Finlandia'),
        ('fr', 'Perancis'),
        ('ga', 'Gabon'),
        ('gm', 'Gambia'),
        ('ge', 'Georgia'),
        ('de', 'Jerman'),
        ('gh', 'Ghana'),
        ('gr', 'Yunani'),
        ('gt', 'Guatemala'),
        ('gn', 'Guinea'),
        ('gw', 'Guinea-Bissau'),
        ('gy', 'Guyana'),
        ('ht', 'Haiti'),
        ('hn', 'Honduras'),
        ('hu', 'Hongaria'),
        ('is', 'Islandia'),
        ('in', 'India'),
        ('id', 'Indonesia'),
        ('ir', 'Iran'),
        ('iq', 'Irak'),
        ('ie', 'Irlandia'),
        ('il', 'Israel'),
        ('it', 'Italia'),
        ('jm', 'Jamaika'),
        ('jp', 'Jepang'),
        ('jo', 'Yordania'),
        ('kz', 'Kazakhstan'),
        ('ke', 'Kenya'),
        ('ki', 'Kiribati'),
        ('kr', 'Korea Selatan'),
        ('kw', 'Kuwait'),
        ('kg', 'Kirgizstan'),
        ('la', 'Laos'),
        ('lv', 'Latvia'),
        ('lb', 'Libanon'),
        ('ls', 'Lesotho'),
        ('lr', 'Liberia'),
        ('ly', 'Libya'),
        ('li', 'Liechtenstein'),
        ('lt', 'Lituania'),
        ('lu', 'Luxembourg'),
        ('mk', 'Makedonia Utara'),
        ('mg', 'Madagaskar'),
        ('mw', 'Malawi'),
        ('my', 'Malaysia'),
        ('mv', 'Maladewa'),
        ('ml', 'Mali'),
        ('mt', 'Malta'),
        ('mh', 'Kepulauan Marshall'),
        ('mr', 'Mauritania'),
        ('mu', 'Mauritius'),
        ('mx', 'Meksiko'),
        ('fm', 'Micronesia'),
        ('md', 'Moldova'),
        ('mc', 'Monako'),
        ('mn', 'Mongolia'),
        ('me', 'Montenegro'),
        ('ma', 'Maroko'),
        ('mz', 'Mozambik'),
        ('mm', 'Myanmar'),
        ('na', 'Namibia'),
        ('np', 'Nepal'),
        ('nl', 'Belanda'),
        ('nz', 'Selandia Baru'),
        ('ni', 'Nikaragua'),
        ('ne', 'Niger'),
        ('ng', 'Nigeria'),
        ('no', 'Norwegia'),
        ('om', 'Oman'),
        ('pk', 'Pakistan'),
        ('pw', 'Palau'),
        ('pa', 'Panama'),
        ('pg', 'Papua Nugini'),
        ('py', 'Paraguay'),
        ('pe', 'Peru'),
        ('ph', 'Filipina'),
        ('pl', 'Polandia'),
        ('pt', 'Portugal'),
        ('qa', 'Qatar'),
        ('ro', 'Rumania'),
        ('ru', 'Rusia'),
        ('rw', 'Rwanda'),
        ('ws', 'Samoa'),
        ('st', 'São Tomé dan Príncipe'),
        ('sa', 'Arab Saudi'),
        ('sn', 'Senegal'),
        ('rs', 'Serbia'),
        ('sc', 'Seychelles'),
        ('sl', 'Sierra Leone'),
        ('sg', 'Singapura'),
        ('sk', 'Slovakia'),
        ('si', 'Slovenia'),
        ('sb', 'Kepulauan Solomon'),
        ('so', 'Somalia'),
        ('za', 'Afrika Selatan'),
        ('es', 'Spanyol'),
        ('lk', 'Sri Lanka'),
        ('sd', 'Sudan'),
        ('sr', 'Suriname'),
        ('se', 'Swedia'),
        ('ch', 'Swiss'),
        ('sy', 'Suriah'),
        ('tw', 'Taiwan'),
        ('tj', 'Tajikistan'),
        ('tz', 'Tanzania'),
        ('th', 'Thailand'),
        ('tl', 'Timor Leste'),
        ('tg', 'Togo'),
        ('to', 'Tonga'),
        ('tt', 'Trinidad dan Tobago'),
        ('tn', 'Tunisia'),
        ('tr', 'Turki'),
        ('tm', 'Turkmenistan'),
        ('ug', 'Uganda'),
        ('ua', 'Ukraina'),
        ('ae', 'Uni Emirat Arab'),
        ('gb', 'Inggris'),
        ('us', 'Amerika Serikat'),
        ('uy', 'Uruguay'),
        ('uz', 'Uzbekistan'),
        ('vu', 'Vanuatu'),
        ('va', 'Vatikans'),
        ('ve', 'Venezuela'),
        ('vn', 'Vietnam'),
        ('ye', 'Yaman'),
        ('zm', 'Zambia'),
        ('zw', 'Zimbabwe'),
        ('ps', 'Palestina')  # Palestina ditambahkan
    ]

    email = models.EmailField(_("email address"), unique=True)  # Menambahkan unique=True
    phone = models.CharField(max_length=20, blank=True, null=True)
    
    country = models.CharField(
        max_length=2,
        choices=choice_country,
        null=True,  # Mengizinkan nilai null di database
        blank=True,  # Mengizinkan form kosong
        default='id'  # Indonesia sebagai default
    )
    birth = models.DateField(null=True, blank=True)
    photo = models.ImageField(upload_to='profile_pics/', blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    hobby = models.CharField(_("hobby"), max_length=150, blank=True)
    education = models.CharField(
        _("education"),
        max_length=20,
        choices=EDUCATION_CHOICES,
        blank=True,
        null=True
    )

    gender = models.CharField(
        _("gender"),
        max_length=10,
        choices=GENDER_CHOICES,
        blank=True,
        null=True
    )

    university = models.ForeignKey(Universiti, on_delete=models.CASCADE, blank=True, null=True, verbose_name=_("university"))

    # Social Media Fields
    tiktok = models.CharField(_("tiktok"), max_length=200, blank=True)
    youtube = models.CharField(_("youtube"), max_length=200, blank=True)
    facebook = models.CharField(_("facebook"), max_length=200, blank=True)
    instagram = models.CharField(_("instagram"), max_length=200, blank=True)
    linkedin = models.CharField(_("linkedin"), max_length=200, blank=True)
    twitter = models.CharField(_("twitter"), max_length=200, blank=True)
    interests = models.ManyToManyField(
        'courses.Category',  
        blank=True,
        related_name='users_with_interest'
    )
    # Status Fields
    is_member = models.BooleanField(_("member status"), default=False, help_text=_("Designates whether the user can log into this admin member."))
    is_subscription = models.BooleanField(_("subscription status"), default=False, help_text=_("Designates whether the user can log into this admin subscription."))
    is_instructor = models.BooleanField(_("instructor status"), default=False, help_text=_("Designates whether the user can log into this admin instructor."))
    is_partner = models.BooleanField(_("partner status"), default=False, help_text=_("Designates whether the user can log into this admin partner."))
    is_audit = models.BooleanField(_("audit status"), default=False, help_text=_("Designates whether the user can log into this admin audit."))
    is_learner = models.BooleanField(_("learner status"), default=True, help_text=_("Designates whether the user can log into this admin learner."))
    is_note = models.BooleanField(_("note status"), default=False, help_text=_("Designates whether the user can log into this admin note."))
    is_curation = models.BooleanField(_("curation status"), default=False,  help_text=_("Designates whether the user can log into this admin curation."))
    is_finance = models.BooleanField(_("finance status"), default=False, help_text=_("Designates whether the user can log into this admin finance."))
    is_marketing = models.BooleanField(_("marketing status"), default=False, help_text=_("Designates whether the user can log into this admin marketing."))
    is_support = models.BooleanField(_("support status"), default=False, help_text=_("Designates whether the user can log into this admin support."))
    # Authentication Fields
    EMAIL_FIELD = "email"
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    def __str__(self):
        return self.username
    

    class Meta:
        indexes = [
            models.Index(fields=["email"]),
            models.Index(fields=["is_learner"]),
            models.Index(fields=["is_partner"]),
            models.Index(fields=["university"]),
            models.Index(fields=["gender"]),
            models.Index(fields=["date_joined"]),
            models.Index(fields=["is_active"]),
        ]



class Profile(models.Model):
    user = models.OneToOneField(CustomUser,on_delete=models.CASCADE)
    follows = models.ManyToManyField("self", related_name="followed_by",symmetrical=False,blank=True)
    date_modified = models.DateTimeField(CustomUser,auto_now=True)
    def __str__(self):
        return self.user.username
    


def create_profile(sender, instance, created, **kwargs):
    if created:
        user_profile = Profile(user=instance)
        user_profile.save()
        user_profile.follows.set([instance.profile.id])
        user_profile.save()

    post_save.connect(create_profile,sender=CustomUser)