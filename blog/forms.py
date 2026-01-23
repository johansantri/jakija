from django import forms
import os
from django.core.exceptions import ValidationError
from django.utils.text import slugify
from .models import BlogPost, Tag, BlogComment
from courses.models import BlacklistedKeyword, Course, Category
from django_ckeditor_5.widgets import CKEditor5Widget
from django.utils import timezone
from datetime import timedelta
from PIL import Image as PILImage
import io
from django.core.files.base import ContentFile
from django.db.models import Q


class BlogPostForm(forms.ModelForm):
    content = forms.CharField(widget=CKEditor5Widget())
    related_courses = forms.ModelMultipleChoiceField(
        queryset=Course.objects.none(),
        required=False,
        widget=forms.MultipleHiddenInput  # ❌ User tidak bisa pilih, otomatis
    )
    class Meta:
        model = BlogPost
        fields = ['title', 'content', 'image', 'category', 'tags', 'status']

        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
                'placeholder': 'Enter post title'
            }),
            'content': forms.Textarea(attrs={
                'class': 'w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
                'rows': 8,
                'placeholder': 'Write your content here'
            }),
            'image': forms.ClearableFileInput(attrs={'class': 'w-full text-gray-700'}),
            'category': forms.Select(attrs={
                'class': 'w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500'
            }),
            'tags': forms.SelectMultiple(attrs={
                'class': 'w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
                'multiple': 'multiple'
            }),
            'status': forms.Select(attrs={
                'class': 'w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500'
            }),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = Category.objects.all()
        self.fields['tags'].queryset = Tag.objects.all()

    def clean(self):
        cleaned_data = super().clean()
        title = cleaned_data.get('title')
        if title and self.user:
            base_slug = slugify(title)
            slug = base_slug
            counter = 1
            while BlogPost.objects.filter(slug=slug).exclude(id=self.instance.id if self.instance else None).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            cleaned_data['slug'] = slug

            recent_posts = BlogPost.objects.filter(
                author=self.user,
                title=title,
                date_posted__gte=timezone.now() - timedelta(minutes=5)
            ).exclude(id=self.instance.id if self.instance else None)
            if recent_posts.exists():
                raise ValidationError("You recently posted an article with the same title. Please use a different title or wait a few minutes.")
        return cleaned_data

    def clean_content(self):
        content = self.cleaned_data.get('content')
        if not content:
            raise ValidationError("Content cannot be empty.")
        if len(content.strip()) < 10:
            raise ValidationError("Content is too short. Please write at least 10 characters.")
        
        blacklisted_keywords = BlacklistedKeyword.objects.all()
        content_lower = content.lower()
        for keyword in blacklisted_keywords:
            if keyword.keyword.lower() in content_lower:
                raise ValidationError(f"Content contains inappropriate word: '{keyword.keyword}'. Please revise your content.")
        return content

    def save(self, commit=True):
        blog_post = super().save(commit=False)
        new_image = self.cleaned_data.get('image')

        old_image_name = None
        if blog_post.pk:
            old_post = BlogPost.objects.get(pk=blog_post.pk)
            old_image_name = old_post.image.name if old_post.image else None
        else:
            old_post = None

        # === Hanya proses jika user upload gambar baru ===
        if new_image and (not old_image_name or new_image != old_post.image):
            # Hapus gambar lama jika ada
            if old_image_name:
                old_post.image.delete(save=False)

            # Buka gambar dengan PIL
            image = PILImage.open(new_image)
            if image.mode == 'RGBA':
                image = image.convert('RGB')

            # Resize
            image = image.resize((1200, 628), PILImage.Resampling.LANCZOS)

            # Simpan ke BytesIO sebagai WEBP
            image_io = io.BytesIO()
            quality = 85
            image.save(image_io, format='WEBP', quality=quality)
            image_io.seek(0)

            while image_io.tell() > 100 * 1024 and quality > 10:
                image_io = io.BytesIO()
                quality -= 5
                image.save(image_io, format='WEBP', quality=quality)
                image_io.seek(0)

            # Tentukan nama file (sama dengan sebelumnya kalau ada)
            filename = os.path.splitext(old_image_name)[0] + '.webp' if old_image_name else os.path.splitext(new_image.name)[0] + '.webp'
            blog_post.image.save(filename, ContentFile(image_io.read()), save=False)

        # === Simpan instance ===
        if commit:
            blog_post.slug = self.cleaned_data['slug']
            blog_post.save()

            # === Related Courses ===
            related_courses_qs = Course.objects.none()

            if blog_post.category:
                related_courses_qs |= Course.objects.filter(category=blog_post.category).exclude(
                    status_course__status='archived'
                )

            content_text = blog_post.content.lower()
            related_courses_qs |= Course.objects.filter(
                Q(course_name__icontains=blog_post.title) |
                Q(description__icontains=blog_post.title) |
                Q(description__icontains=content_text)
            ).exclude(status_course__status='archived')

            article_tags = blog_post.tags.all()
            tag_names = [tag.name.lower() for tag in article_tags]
            if tag_names:
                related_courses_qs |= Course.objects.filter(
                    Q(level__in=tag_names),
                    ~Q(status_course__status='archived')
                )

            blog_post.related_courses.set(related_courses_qs.distinct())
            self.save_m2m()

        return blog_post



# NewCommentForm tetap sama
class NewCommentForm(forms.ModelForm):
    class Meta:
        model = BlogComment
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={
                'class': 'block p-2.5 w-full text-sm text-gray-900 bg-gray-50 rounded-lg border border-gray-300 focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white dark:focus:ring-blue-500 dark:focus:border-blue-500',
                'placeholder': 'Write your comment here...',
                'rows': 5,
                'aria-label': 'Comment',
                'required': True
            }),
        }
        labels = {
            'content': 'Comment',
        }
        help_texts = {
            'content': 'Keep your comment respectful and relevant.',
        }

    def clean_content(self):
        content = self.cleaned_data.get('content')
        if not content:
            raise ValidationError("Comment cannot be empty.")
        if len(content.strip()) < 5:
            raise ValidationError("Comment is too short. Please write something meaningful.")
        blacklisted_keywords = BlacklistedKeyword.objects.all()
        content_lower = content.lower()
        for keyword in blacklisted_keywords:
            if keyword.keyword.lower() in content_lower:
                raise ValidationError(
                    f"Comment contains inappropriate word: '{keyword.keyword}'. Please revise your comment."
                )
        return content