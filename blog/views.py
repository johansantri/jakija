from django.views.generic import ListView, DetailView
from django.shortcuts import render,get_object_or_404, redirect
from .models import BlogPost, Tag, BlogComment
from .forms import NewCommentForm,BlogPostForm
from courses.models import Course, Category as CourseCategory
from django.urls import reverse
from django.contrib.auth.views import redirect_to_login
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib import messages
from django.urls import reverse_lazy
from django_ratelimit.decorators import ratelimit  # Untuk rate-limiting
from django.utils.decorators import method_decorator
from django.core.exceptions import PermissionDenied
from django.utils import timezone
from datetime import timedelta
from django.db.models import Q
from django.core.cache import cache
from django.core.paginator import Paginator

# View baru untuk CRUD
class BlogPostCreateView(LoginRequiredMixin, CreateView):
    model = BlogPost
    form_class = BlogPostForm
    template_name = 'blog/blog_form.html'
    success_url = reverse_lazy('blog:blog-list-admin')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def dispatch(self, *args, **kwargs):
        # Cek apakah user memiliki izin yang diperlukan
        if not (self.request.user.is_superuser or self.request.user.is_staff or self.request.user.is_partner or self.request.user.is_instructor):
            messages.error(self.request, 'You do not have permission to create a blog post.')
            return redirect('blog:blog-list-admin')  # Atau halaman lain sesuai kebutuhan

        # Cek apakah user sudah mencapai batas postingan per jam
        recent_post = BlogPost.objects.filter(
            author=self.request.user,
            date_posted__gte=timezone.now() - timedelta(hours=1)
        ).count()
        if recent_post >= 5:
            messages.error(self.request, 'You have reached the limit of 5 posts per hour. Please try again later.')
            return redirect('blog:blog-list-admin')

        return super().dispatch(*args, **kwargs)

    def form_valid(self, form):
        # Set author sebagai user yang sedang login
        form.instance.author = self.request.user
        messages.success(self.request, 'Blog post created successfully!')
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, 'There was an error creating the blog post. Please check the form.')
        return super().form_invalid(form)
    
class BlogPostUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = BlogPost
    form_class = BlogPostForm
    template_name = 'blog/blog_form.html'
    success_url = reverse_lazy('blog:blog-list-admin')

    def test_func(self):
        post = self.get_object()
        # Pengecekan jika user yang sedang login adalah author post atau memiliki status yang diizinkan
        return self.request.user == post.author or self.request.user.is_superuser or self.request.user.is_staff or self.request.user.is_partner or self.request.user.is_instructor

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def dispatch(self, *args, **kwargs):
        # Pengecekan apakah user sudah mencapai batas edit per jam
        recent_edits = BlogPost.objects.filter(
            author=self.request.user,
            date_updated__gte=timezone.now() - timedelta(hours=1)
        ).count()

        if recent_edits >= 10:
            messages.error(self.request, 'You have reached the limit of 10 edits per hour. Please try again later.')
            return redirect('blog:blog-list-admin')

        # Pengecekan hak akses: jika user tidak diperbolehkan mengedit, redirect ke halaman lain
        if not (self.request.user.is_superuser or self.request.user.is_staff or self.request.user.is_partner or self.request.user.is_instructor):
            messages.error(self.request, 'You do not have permission to edit this blog post.')
            return redirect('blog:blog-list-admin')

        return super().dispatch(*args, **kwargs)

    def form_valid(self, form):
        messages.success(self.request, 'Blog post updated successfully!')
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, 'There was an error updating the blog post. Please check the form.')
        return super().form_invalid(form)

class BlogPostDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = BlogPost
    template_name = 'blog/blog_confirm_delete.html'
    success_url = reverse_lazy('blog:blog-list-admin')

    def test_func(self):
        # Hanya 'superuser' yang dapat menghapus artikel
        return self.request.user.is_superuser

    def dispatch(self, *args, **kwargs):
        # Rate-limiting: cek jumlah penghapusan (status='deleted') dalam 1 jam
        recent_deletions = BlogPost.objects.filter(
            author=self.request.user,
            status='deleted',
            date_updated__gte=timezone.now() - timedelta(hours=1)
        ).count()

        if recent_deletions >= 5:
            messages.error(self.request, 'You have reached the limit of 5 deletions per hour. Please try again later.')
            return redirect('blog:blog-list-admin')

        return super().dispatch(*args, **kwargs)

    def delete(self, request, *args, **kwargs):
        # Soft delete: set status='deleted'
        self.object = self.get_object()
        self.object.status = 'deleted'
        self.object.save()
        messages.success(self.request, 'Blog post deleted successfully!')
        return redirect(self.success_url)

class BlogPostListAdminView(LoginRequiredMixin, ListView):
    model = BlogPost
    template_name = 'blog/blog_list_admin.html'
    context_object_name = 'posts'
    paginate_by = 10

    required_fields = {
        'first_name': 'First Name',
        'last_name': 'Last Name',
        'email': 'Email',
        'phone': 'Phone Number',
        'gender': 'Gender',
        'birth': 'Date of Birth',
    }

    def dispatch(self, request, *args, **kwargs):
        user = request.user
        missing_fields = [
            label for field, label in self.required_fields.items() if not getattr(user, field)
        ]
        if missing_fields:
            messages.warning(
                request,
                f"Please complete the following information: {', '.join(missing_fields)}"
            )
            return redirect('authentication:edit-profile', pk=user.pk)

        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        user = self.request.user
        cache_key = (
            f'blog_posts_{user.id}_'
            f'q_{self.request.GET.get("q", "")}_'
            f'status_{self.request.GET.get("status", "")}_'
            f'category_{self.request.GET.get("category", "")}_'
            f'tag_{self.request.GET.get("tag", "")}'
        )

        cached_queryset = cache.get(cache_key)
        if cached_queryset:
            return cached_queryset

        queryset = BlogPost.objects.exclude(status='deleted')
        queryset = queryset.select_related('author', 'category').prefetch_related('tags')

        search_query = self.request.GET.get('q', '')
        if search_query:
            queryset = queryset.filter(Q(title__icontains=search_query) | Q(content__icontains=search_query))

        status = self.request.GET.get('status', '')
        if status in ['draft', 'published']:
            queryset = queryset.filter(status=status)

        category_id = self.request.GET.get('category', '')
        if category_id:
            queryset = queryset.filter(category__id=category_id)

        tag_id = self.request.GET.get('tag', '')
        if tag_id:
            queryset = queryset.filter(tags__id=tag_id)

        if not user.is_superuser:
            queryset = queryset.filter(author=user)

        queryset = queryset.order_by('-date_posted')

        cache.set(cache_key, queryset, 300)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'title': 'Manage Blog Posts',
            'categories': CourseCategory.objects.all(),
            'tags': Tag.objects.all(),
            'status_choices': BlogPost.STATUS_CHOICES[:2],  # draft & published only
            'search_query': self.request.GET.get('q', ''),
            'selected_status': self.request.GET.get('status', ''),
            'selected_category': self.request.GET.get('category', ''),
            'selected_tag': self.request.GET.get('tag', ''),
        })
        return context



class BlogListView(ListView):
    model = BlogPost
    template_name = 'blog/blog_list.html'
    context_object_name = 'posts'
    paginate_by = 6

    def get_queryset(self):
        return BlogPost.objects.filter(status='published').order_by('-date_posted')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        categories = CourseCategory.objects.filter(blogpost__status='published').distinct()
        context['categories'] = [
            {
                'category': cat,
                'post_count': cat.blogpost_set.filter(status='published').count(),
                'url': reverse('blog:category-posts', kwargs={'slug': cat.slug})  # Sekarang menghasilkan /blog/category/<slug>/
            }
            for cat in categories
        ]
        tags = Tag.objects.filter(blogpost__status='published').distinct()
        context['tags'] = [
            {'tag': tag, 'post_count': tag.blogpost_set.filter(status='published').count()}
            for tag in tags
        ]
        return context

class BlogDetailView(DetailView):
    model = BlogPost
    template_name = 'blog/blog_detail.html'
    context_object_name = 'post'

    def get_queryset(self):
        return BlogPost.objects.filter(status='published')

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        obj.views += 1
        obj.save()
        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Fetch related posts (same category, exclude current post)
        related_posts = BlogPost.objects.filter(
            category=self.object.category, status='published'
        ).exclude(id=self.object.id).order_by('-date_posted')[:5]
        
        # If not enough related posts, try matching by tags
        if len(related_posts) < 3 and self.object.tags.exists():
            tag_related = BlogPost.objects.filter(
                tags__in=self.object.tags.all(), status='published'
            ).exclude(id=self.object.id).order_by('-date_posted')[:5 - len(related_posts)]
            related_posts = list(related_posts) + list(tag_related)
        
        # Remove duplicates using set() and ensure uniqueness
        context['related_posts'] = list({post.id: post for post in related_posts}.values())[:5]
        
        # Paginasi komentar
        comments = self.object.comments.filter(parent__isnull=True).order_by('-date_posted')
        paginator = Paginator(comments, 10)  # 10 komentar per halaman
        page_number = self.request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        context['comments'] = page_obj
        
        context['comment_form'] = NewCommentForm()

        # Fetching and processing categories and tags
        categories = CourseCategory.objects.filter(blogpost__status='published').distinct()
        context['categories'] = [
            {
                'category': cat,
                'post_count': cat.blogpost_set.filter(status='published').count(),
                'url': reverse('blog:category-posts', kwargs={'slug': cat.slug})
            }
            for cat in categories
        ]
        
        tags = Tag.objects.filter(blogpost__status='published').distinct()
        context['tags'] = [
            {'tag': tag, 'post_count': tag.blogpost_set.filter(status='published').count()}
            for tag in tags
        ]
        
        courses = self.object.related_courses.filter(
            status_course__status='published',  # <- tambahkan filter ini
            id__isnull=False,
            slug__isnull=False
        ).exclude(slug='').order_by('-id')  # agar versi terbaru muncul lebih dulu

            
        # Gunakan slug untuk menghindari kursus duplikat (ID yang berbeda, slug yang sama)
        unique_courses = {course.slug: course for course in courses}.values()
        context['related_courses'] = list(unique_courses)
        
        return context

    def post(self, request, *args, **kwargs):
        # Ensure the object is fetched
        self.object = self.get_object()  # Set self.object explicitly
        form = NewCommentForm(request.POST)

        if form.is_valid():
            if not request.user.is_authenticated:
                # Redirect to login with 'next' parameter to return to this page
                next_url = reverse('blog:blog-detail', kwargs={'slug': self.object.slug})
                return redirect(next_url)  # Redirect to login page
            
            # Check the time of the user's last comment
            last_comment = self.object.comments.filter(author=request.user).order_by('-date_posted').first()
            if last_comment and last_comment.date_posted > timezone.now() - timedelta(seconds=60):
                # If last comment was made less than 60 seconds ago, show error
                form.add_error(None, "You are posting too quickly. Please wait a few seconds before commenting again.")
                context = self.get_context_data()
                context['comment_form'] = form
                return render(request, self.template_name, context)

            # Save the comment for authenticated users
            comment = form.save(commit=False)
            comment.blogpost_connected = self.object
            comment.author = request.user  # Set the authenticated user as the author
            
            # Validate parent_id safely for threaded comments
            parent_id = request.POST.get('parent_id')
            if parent_id:
                try:
                    parent = get_object_or_404(BlogComment, id=int(parent_id), blogpost_connected=self.object)
                    comment.parent = parent
                except (ValueError, BlogComment.DoesNotExist):
                    # If parent comment doesn't exist or invalid, we skip assigning parent
                    pass
            
            comment.save()
            return redirect('blog:blog-detail', slug=self.object.slug)
        
        # If form is invalid, render the template with the form and context
        context = self.get_context_data()
        context['comment_form'] = form
        return render(request, self.template_name, context)


class CategoryPostListView(ListView):
    model = BlogPost
    template_name = 'blog/blog_list.html'
    context_object_name = 'posts'
    paginate_by = 6

    def get_queryset(self):
        category = get_object_or_404(CourseCategory, slug=self.kwargs['slug'])
        queryset = BlogPost.objects.filter(category=category, status='published').order_by('-date_posted')
        print(f"Category: {category}, Posts: {queryset}")  # Debugging
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        categories = CourseCategory.objects.filter(blogpost__status='published').distinct()
        context['categories'] = [
            {
                'category': cat,
                'post_count': cat.blogpost_set.filter(status='published').count(),
                'url': reverse('blog:category-posts', kwargs={'slug': cat.slug})  # Sekarang menghasilkan /blog/category/<slug>/
            }
            for cat in categories
        ]
        context['tags'] = Tag.objects.filter(blogpost__status='published').distinct()
        context['current_category'] = get_object_or_404(CourseCategory, slug=self.kwargs['slug'])
        print(f"Context keys: {context.keys()}")  # Debugging
        return context

    def render_to_response(self, context, **response_kwargs):
        print(f"Rendering template: {self.template_name}")  # Debugging
        return super().render_to_response(context, **response_kwargs)

class TagPostListView(ListView):
    model = BlogPost
    template_name = 'blog/blog_list.html'
    context_object_name = 'posts'
    paginate_by = 6

    def get_queryset(self):
        tag = get_object_or_404(Tag, slug=self.kwargs['slug'])
        posts = BlogPost.objects.filter(tags=tag, status='published').order_by('-date_posted')
        print(f"Tag: {tag}, Posts: {posts}")  # Debugging
        return posts

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        categories = CourseCategory.objects.filter(blogpost__status='published').distinct()
        context['categories'] = [
            {'category': cat, 'post_count': cat.blogpost_set.filter(status='published').count()}
            for cat in categories
        ]
        context['tags'] = [
            {'tag': tag, 'post_count': tag.blogpost_set.filter(status='published').count()}
            for tag in Tag.objects.all().distinct()
        ]
        context['current_tag'] = get_object_or_404(Tag, slug=self.kwargs['slug'])
        return context