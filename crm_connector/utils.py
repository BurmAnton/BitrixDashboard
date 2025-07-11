from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

def safe_decimal(value, default=0):
    """
    Безопасно конвертирует значение в Decimal.
    Возвращает default, если конвертация невозможна.
    """
    try:
        return Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        return Decimal(default)
    
def format_currency(value):
    """
    Форматирует число как валюту с разделителями тысяч.
    """
    try:
        # Округляем до целого
        decimal_value = safe_decimal(value).quantize(Decimal('1.'), rounding=ROUND_HALF_UP)
        # Форматируем с разделителем тысяч
        return f"{decimal_value:,}".replace(",", " ")
    except (ValueError, TypeError, InvalidOperation):
        return "0" 

def get_success_deals_stats(pipeline_id):
    """
    Возвращает статистику по успешным сделкам в воронке
    """
    from .models import Deal, Stage
    from django.db.models import Sum, Count
    
    # Находим стадии успешного завершения
    success_stages = Stage.objects.filter(
        pipeline_id=pipeline_id, 
        type='success'
    )
    
    # Получаем суммы и количество успешных сделок
    success_deals = Deal.objects.filter(
        pipeline_id=pipeline_id,
        stage__in=success_stages
    )
    
    stats = {
        'count': success_deals.count(),
        'amount': success_deals.aggregate(total=Sum('amount'))['total'] or 0
    }
    
    return stats 

# ------------------------------------------------------------------
# Определение стадии сделки по статусам Атлас / РР
# ------------------------------------------------------------------

from typing import Optional, Dict

def determine_stage_for_statuses(pipeline, atlas_status: str, rr_status: str, field_mapping: Dict) -> Optional[str]:
    """Возвращает ID стадии (формат C<cat>:<code>) по переданным статусам.

    1. Сначала используется StageRule (динамические правила из БД).
    2. Если ни одно правило не подошло – fallback на `stage_mapping` в JSON-конфиге.
    3. Если и там нет совпадений, берётся `pipeline_settings.default_stage` либо 'NEW'.

    :param pipeline: модель Pipeline, к которой относится сделка.
    :param atlas_status: строка статуса Атлас (может быть '').
    :param rr_status: строка статуса РР (может быть '').
    :param field_mapping: содержимое atlas_field_mapping.json (dict).
    :return: строка вида "C<PIPELINE_ID>:<STAGE_CODE>" или None, если pipeline None.
    """
    if pipeline is None:
        return None

    from .models import StageRule  # локальный импорт во избежание циклов

    atlas_status = (atlas_status or '').strip()
    rr_status = (rr_status or '').strip()

    # 1) динамические правила
    stage = StageRule.determine_stage_for_deal(
        pipeline=pipeline,
        atlas_status_name=atlas_status or None,
        rr_status_name=rr_status or None,
    )
    if stage:
        return stage.bitrix_id

    # 2) статическая карта из JSON
    stage_map = field_mapping.get('stage_mapping', {}) if field_mapping else {}
    stage_code = None
    if rr_status and rr_status in stage_map:
        stage_code = stage_map[rr_status]
    elif atlas_status and atlas_status in stage_map:
        stage_code = stage_map[atlas_status]
    else:
        stage_code = field_mapping.get('pipeline_settings', {}).get('default_stage', 'NEW') if field_mapping else 'NEW'

    return f"C{pipeline.bitrix_id}:{stage_code}" 