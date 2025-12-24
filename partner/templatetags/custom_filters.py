from django import template

register = template.Library()

@register.filter
def index(List, i):
    try:
        return List[i % len(List)]
    except:
        return ''


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)
@register.filter
def get_item(dictionary, key):
    """Get the value from dictionary by key."""
    return dictionary.get(key)

@register.filter
def get_item(dictionary, key):
    """Mengambil item dari dictionary berdasarkan key"""
    return dictionary.get(key)

@register.inclusion_tag('partner/comment_tree.html', takes_context=True)
def render_comment_tree(context, comment):
    request = context['request']
    return {
        'comment': comment,
        'replies': comment.get_replies(),
        'request': request,
    }

#Untuk mengambil nilai list dalam ChartJS:
@register.filter
def pluck(value, key):
    return [v[key] for v in value]




@register.filter
def zip_lists(a, b):
    return zip(a, b)


@register.filter
def dict_get_safe(dict_obj, key):
    if dict_obj and key in dict_obj:
        return dict_obj[key]
    return []