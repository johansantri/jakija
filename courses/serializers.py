from rest_framework import serializers
from .models import Section
from slugify import slugify

class SectionSerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()
    type = serializers.SerializerMethodField()

    class Meta:
        model = Section
        fields = ['id', 'title', 'slug', 'type', 'order', 'parent', 'courses', 'children']

    def get_children(self, obj):
        # Pastikan hanya children yang terkait dengan section ini yang diambil
        children_qs = obj.children.all().order_by('order')  # Hanya ambil children yang sudah di-ordered
        return SectionSerializer(children_qs, many=True).data

    def get_type(self, obj):
        if obj.parent is None:
            return 'section'  # section adalah level utama
        elif obj.children.exists():
            return 'subsection'  # subsection adalah level kedua, memiliki children
        else:
            return 'unit'  # unit adalah level paling bawah yang tidak memiliki children
    def validate(self, data):
        # Hanya cek "parent to itself" saat UPDATE (self.instance ada)
        if self.instance and 'parent' in data and data['parent'] == self.instance:
            raise serializers.ValidationError("Cannot set parent to itself.")
        return data
    
    def update(self, instance, validated_data):
        # Jika title berubah, regenerate slug manual jika perlu
        if 'title' in validated_data:
            instance.title = validated_data['title']
            instance.slug = slugify(instance.title)  # Asumsi AutoSlugField pakai slugify
            # Cek unique manual
            if Section.objects.filter(slug=instance.slug, parent=instance.parent).exclude(pk=instance.pk).exists():
                raise serializers.ValidationError("Slug already exists under this parent.")
        return super().update(instance, validated_data)
