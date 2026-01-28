# blog/urls.py
from django.urls import path
from . import views

app_name = 'blog'

urlpatterns = [
    path('blog/', views.BlogListView.as_view(), name='blog-list'),
    path('post/<slug:slug>/', views.BlogDetailView.as_view(), name='blog-detail'),
    path('blog/category/<slug:slug>/', views.CategoryPostListView.as_view(), name='category-posts'),
    path('tag/<slug:slug>/', views.TagPostListView.as_view(), name='tag-posts'),
    path('admin/posts/all', views.BlogPostListAdminView.as_view(), name='blog-list-admin'),
    path('admin/post/create/', views.BlogPostCreateView.as_view(), name='blog-create'),
    path('admin/post/<int:pk>/update/', views.BlogPostUpdateView.as_view(), name='blog-update'),
    path('admin/post/<int:pk>/delete/', views.BlogPostDeleteView.as_view(), name='blog-delete'),
    path('admin/post/<int:post_id>/comments/', views.BlogPostCommentListView.as_view(), name='blog-comment-list'),
    # URL reply komentar
    path('admin/comment/<int:comment_id>/reply/', views.BlogCommentReplyView.as_view(), name='comment-reply'),

    # URL hapus komentar
    path('admin/comment/<int:comment_id>/delete/', views.BlogCommentDeleteView.as_view(), name='comment-delete'),
    path('mark-read/', views.mark_blog_read, name='mark-blog-read'),
    path('blog/admin/analytics/', views.blog_analytics_dashboard, name='blog-analytics')
   
]