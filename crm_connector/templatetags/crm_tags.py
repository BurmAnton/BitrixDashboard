from django import template
from decimal import Decimal

register = template.Library()

@register.filter
def multiply(value, arg):
    """Умножает значение на аргумент"""
    try:
        # Конвертируем оба значения в Decimal для точности
        return Decimal(str(value)) * Decimal(str(arg))
    except (ValueError, TypeError):
        return 0

@register.filter
def divide(value, arg):
    """Делит значение на аргумент"""
    try:
        # Конвертируем оба значения в Decimal для точности
        arg = Decimal(str(arg))
        if arg == 0:
            return 0
        return Decimal(str(value)) / arg
    except (ValueError, TypeError):
        return 0

@register.filter
def currency(value):
    """Форматирует число как валюту"""
    if value is None:
        return "0 ₽"
    
    # Преобразуем в Decimal если это не Decimal
    if not isinstance(value, Decimal):
        try:
            value = Decimal(str(value))
        except:
            return f"{value} ₽"
    
    # Форматируем с разделителями тысяч
    formatted = f"{value:,.2f}".replace(",", " ").replace(".", ",")
    return f"{formatted} ₽"

@register.filter
def sum_percent(stage_types):
    """Возвращает сумму процентов всех типов этапов"""
    return sum(stage_type.get('percent', 0) for stage_type in stage_types)

@register.filter
def css_float(value):
    """
    Преобразует число в строку с точкой в качестве десятичного разделителя для использования в CSS.
    Например: 10,5 -> 10.5
    """
    try:
        # Преобразуем в строку и заменяем запятую на точку, если она есть
        return str(value).replace(',', '.')
    except (ValueError, TypeError):
        return value

@register.filter
def getattr(obj, attr):
    """Получает атрибут объекта по имени"""
    return getattr(obj, attr, None) 