from django import template
from decimal import Decimal

register = template.Library()
 
@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)

@register.filter
def sum_total_places(agreements):
    """Вычисляет общее количество мест по всем договорам"""
    total = 0
    for agreement in agreements:
        total += agreement.get_total_quota_places()
    return total

@register.filter
def sum_total_cost(agreements):
    """Вычисляет общую стоимость по всем договорам"""
    total = Decimal('0')
    for agreement in agreements:
        total += agreement.get_total_agreement_cost()
    return total

@register.filter
def div(value, divisor):
    """Деление двух чисел"""
    try:
        return float(value) / float(divisor)
    except (ValueError, ZeroDivisionError, TypeError):
        return 0 