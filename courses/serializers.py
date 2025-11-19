from rest_framework import serializers
from .models import Section, Material, Assessment  # pastikan import Material
# from .models import Assessment  # ← kalau kamu punya model Assessment
from slugify import slugify


# Serializer untuk Material (bisa dipisah ke file tersendiri nanti kalau mau)
class MaterialSerializer(serializers.ModelSerializer):
    class Meta:
        model = Material
        fields = ['id', 'title', 'description','section']  # tambah field lain kalau perlu
        extra_kwargs = {
            'section': {'required': True}
        }


# Kalau kamu punya model Assessment, buat juga serializer-nya
class AssessmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Assessment
        fields = ['id', 'name', 'weight', 'section']  # tambah field lain kalau perlu
        extra_kwargs = {
            'section': {'required': True}
        }


class SectionSerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()
    type = serializers.SerializerMethodField()

    # Tambahkan ini → hanya muncul di level unit
    materials = MaterialSerializer(many=True, read_only=True)
    assessments = AssessmentSerializer(many=True, read_only=True)  # uncomment kalau ada

    class Meta:
        model = Section
        fields = [
            'id', 'title', 'slug', 'type', 'order',
            'parent', 'courses', 'children',
            'materials',           # ← BARU
            'assessments',       # ← BARU (uncomment kalau pakai)
        ]

    def get_children(self, obj):
        children_qs = obj.children.all().order_by('order')
        return SectionSerializer(children_qs, many=True, context=self.context).data

    def get_type(self, obj):
        if obj.parent is None:
            return 'section'
        elif obj.children.exists():  # subsection punya anak (unit)
            return 'subsection'
        else:
            return 'unit'

    # Validasi parent tidak boleh diri sendiri
    def validate(self, data):
        if self.instance and 'parent' in data and data['parent'] == self.instance:
            raise serializers.ValidationError("Cannot set parent to itself.")
        return data

    # Update title + slug (karena AutoSlugField kadang tidak langsung jalan di PATCH)
    def update(self, instance, validated_data):
        if 'title' in validated_data:
            instance.title = validated_data['title']
            new_slug = slugify(instance.title)
            # Cek slug unik di level parent yang sama
            if Section.objects.filter(slug=new_slug, parent=instance.parent).exclude(pk=instance.pk).exists():
                raise serializers.ValidationError("Slug already exists under this parent.")
            instance.slug = new_slug
        return super().update(instance, validated_data)