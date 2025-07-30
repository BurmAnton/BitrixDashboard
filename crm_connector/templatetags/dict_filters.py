from django import template

register = template.Library()

@register.filter
def sum_values(dictionary):
    """Суммирует все значения словаря"""
    if not dictionary:
        return 0
    # Если это уже dict_values объект
    if hasattr(dictionary, '__iter__') and not isinstance(dictionary, (str, dict)):
        return sum(dictionary)
    # Если это словарь
    if isinstance(dictionary, dict):
        return sum(dictionary.values())
    return 0

@register.filter
def dict_get(dictionary, key):
    """Получает значение из словаря по ключу"""
    if not dictionary:
        return None
    return dictionary.get(key)