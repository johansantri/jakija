from django.contrib import admin
from .models import Tag, BlogPost, BlogComment
from django.utils.html import format_html
from django.urls import reverse
from courses.models import Course




@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'post_count')
    list_filter = ('name',)
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    
    def post_count(self, obj):
        return obj.blogpost_set.count()
    post_count.short_description = 'Number of Posts'

@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'category', 'status', 'views', 'date_posted', 'comment_count', 'related_courses_list')
    list_filter = ('status', 'category', 'tags', 'date_posted')
    search_fields = ('title', 'content', 'author__username')
    prepopulated_fields = {'slug': ('title',)}
    filter_horizontal = ('tags', 'related_courses')
    date_hierarchy = 'date_posted'
    actions = ['mark_as_published', 'mark_as_draft']
    
    def comment_count(self, obj):
        return obj.number_of_comments
    comment_count.short_description = 'Comments'

    def related_courses_list(self, obj):
        courses = obj.related_courses.all()
        if courses:
            return format_html(', '.join(
                f'<a href="{reverse("admin:courses_course_change", args=[course.pk])}">{course.course_name}</a>'
                for course in courses
            ))
        return '-'
    related_courses_list.short_description = 'Related Courses'

    def mark_as_published(self, request, queryset):
        queryset.update(status='published')
    mark_as_published.short_description = 'Mark selected posts as Published'

    def mark_as_draft(self, request, queryset):
        queryset.update(status='draft')
    mark_as_draft.short_description = 'Mark selected posts as Draft'

@admin.register(BlogComment)
class BlogCommentAdmin(admin.ModelAdmin):
    list_display = ('author', 'blogpost_connected', 'parent_comment', 'date_posted', 'content_preview')
    list_filter = ('date_posted', 'blogpost_connected')
    search_fields = ('author', 'content', 'blogpost_connected__title')
    list_select_related = ('blogpost_connected', 'parent')
    readonly_fields = ('date_posted',)

    def parent_comment(self, obj):
        if obj.parent:
            return format_html(
                f'<a href="{reverse("admin:blog_blogcomment_change", args=[obj.parent.pk])}">{obj.parent.author}</a>'
            )
        return '-'
    parent_comment.short_description = 'Parent Comment'

    def content_preview(self, obj):
        return obj.content[:50] + ('...' if len(obj.content) > 50 else '')
    content_preview.short_description = 'Content'