from django.db import models
from authentication.models import CustomUser, Universiti
from django.utils import timezone
from django.urls import reverse
from courses.models import Category, Course

class Tag(models.Model):
    name = models.CharField(max_length=50)
    slug = models.SlugField(max_length=50, unique=True)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('blog:tag-posts', kwargs={'slug': self.slug})

class BlogPost(models.Model):
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('deleted', 'Deleted'),
    )
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    content = models.TextField()
    image = models.ImageField(upload_to='blog_images/', blank=True, null=True)
    author = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True)
    tags = models.ManyToManyField(Tag, blank=True)
    related_courses = models.ManyToManyField(Course, blank=True, related_name='related_posts')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    views = models.PositiveIntegerField(default=0)
    date_posted = models.DateTimeField(default=timezone.now)
    date_updated = models.DateTimeField(auto_now=True)
    last_comment_checked = models.DateTimeField(default=timezone.now)  # baru ditambahkan
    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('blog:blog-detail', kwargs={'slug': self.slug})

    @property
    def number_of_comments(self):
        return self.comments.count()
    class Meta:
        ordering = ['-date_posted']

class BlogComment(models.Model):
    blogpost_connected = models.ForeignKey(BlogPost, related_name='comments', on_delete=models.CASCADE)
    parent = models.ForeignKey('self', null=True, blank=True, related_name='replies', on_delete=models.CASCADE)
    author = models.ForeignKey(CustomUser, on_delete=models.CASCADE) 
    content = models.TextField()
    date_posted = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f'Comment by {self.author} on {self.blogpost_connected.title}'
    
class Notification(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    message = models.TextField()
    link = models.CharField(max_length=255, blank=True)
    read = models.BooleanField(default=False)
    date_created = models.DateTimeField(auto_now_add=True)



class BlogPostRead(models.Model):
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    session_key = models.CharField(max_length=40, db_index=True)
    blogpost = models.ForeignKey(
        BlogPost,
        on_delete=models.CASCADE,
        related_name='reads'
    )
    read_at = models.DateTimeField(auto_now_add=True)
    duration = models.PositiveIntegerField(help_text="Seconds spent reading")
    is_completed = models.BooleanField(default=False)

    class Meta:
        unique_together = ('session_key', 'blogpost')