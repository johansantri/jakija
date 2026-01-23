from django import template

register = template.Library()

@register.filter
def div(value, divisor):
    try:
        return float(value) / float(divisor)
    except (ValueError, ZeroDivisionError):
        return 0
    
@register.filter
def add_class(field, css_class):
    """
    Add CSS classes to a form field's widget.
    """
    return field.as_widget(attrs={"class": css_class})

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)