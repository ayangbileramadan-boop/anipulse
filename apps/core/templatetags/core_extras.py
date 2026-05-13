from django import template

register = template.Library()


@register.filter
def div(value, arg):
    try:
        return int(value) / int(arg)
    except (ValueError, ZeroDivisionError):
        return 0


@register.filter
def hours_from_seconds(value):
    try:
        return int(value) // 3600
    except (ValueError, TypeError):
        return 0


@register.filter
def minutes_remainder(value):
    try:
        return (int(value) % 3600) // 60
    except (ValueError, TypeError):
        return 0


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key, [])


@register.simple_tag(takes_context=True)
def url_replace(context, **kwargs):
    query = context['request'].GET.copy()
    for k, v in kwargs.items():
        query[k] = v
    return query.urlencode()
