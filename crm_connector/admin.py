from django.contrib import admin
from .models import Pipeline, Stage, Deal, Company, Lead, Contact, AtlasApplication, STAGE_TYPE_CHOICES, AtlasStatus, RRStatus, StageRule, AtlasProgram
from django import forms
from django.contrib import messages
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Count, Sum, Q
from django.utils import timezone
from simple_history.admin import SimpleHistoryAdmin

class StageInline(admin.TabularInline):
    model = Stage
    extra = 0
    fields = ('bitrix_id', 'name', 'sort', 'color', 'status_id', 'success_probability')

@admin.register(Pipeline)
class PipelineAdmin(SimpleHistoryAdmin):
    list_display = ['name', 'bitrix_id', 'is_main', 'is_active', 'sort', 'stage_count', 'deal_count', 'last_sync_display']
    search_fields = ('name', 'bitrix_id')
    list_filter = ('is_active', 'is_main')
    inlines = [StageInline]
    
    def stage_count(self, obj):
        """Количество этапов в воронке"""
        return obj.stages.count()
    stage_count.short_description = 'Этапов'
    
    def deal_count(self, obj):
        """Количество сделок в воронке"""
        return obj.deals.count()
    deal_count.short_description = 'Сделок'
    
    def last_sync_display(self, obj):
        """Отображение времени последней синхронизации"""
        if obj.last_sync:
            return obj.last_sync.strftime('%d.%m.%Y %H:%M')
        return '-'
    last_sync_display.short_description = 'Последняя синхронизация'

@admin.register(Stage)
class StageAdmin(SimpleHistoryAdmin):
    list_display = ['name', 'colored_type', 'pipeline', 'bitrix_id', 'sort', 'deal_count']
    list_filter = ('pipeline', 'type')
    search_fields = ('name',)
    ordering = ('pipeline', 'sort')
    actions = ['set_process_type', 'set_success_type', 'set_failure_type']
    readonly_fields = ('color_display',)
    
    def colored_type(self, obj):
        """Отображает тип стадии с цветом"""
        colors = {
            'process': '#5bc0de',
            'success': '#5cb85c', 
            'failure': '#d9534f'
        }
        color = colors.get(obj.type, '#999')
        return format_html(
            '<span style="display:inline-block; padding: 3px 8px; color: white; background-color: {}; border-radius: 3px;">{}</span>',
            color, obj.get_type_display()
        )
    colored_type.short_description = 'Тип'
    
    def deal_count(self, obj):
        """Количество сделок на этапе"""
        return obj.deals.count()
    deal_count.short_description = 'Сделок'
    
    def color_display(self, obj):
        """Отображает цвет этапа в виде цветного квадрата"""
        if obj.color:
            from django.utils.safestring import mark_safe
            return mark_safe(f'<span style="display:inline-block; width:20px; height:20px; background-color:{obj.color}"></span> {obj.color}')
        return '-'
    color_display.short_description = 'Цвет'
    
    def set_process_type(self, request, queryset):
        """Устанавливает тип 'В процессе' для выбранных стадий"""
        updated = queryset.update(type='process')
        self.message_user(request, f'Обновлено {updated} стадий (тип: В процессе)')
    set_process_type.short_description = "Назначить тип 'В процессе'"
    
    def set_success_type(self, request, queryset):
        """Устанавливает тип 'Успешное завершение' для выбранных стадий"""
        updated = queryset.update(type='success')
        self.message_user(request, f'Обновлено {updated} стадий (тип: Успешное завершение)')
    set_success_type.short_description = "Назначить тип 'Успешное завершение'"
    
    def set_failure_type(self, request, queryset):
        """Устанавливает тип 'Неуспешное завершение' для выбранных стадий"""
        updated = queryset.update(type='failure')
        self.message_user(request, f'Обновлено {updated} стадий (тип: Неуспешное завершение)')
    set_failure_type.short_description = "Назначить тип 'Неуспешное завершение'"

@admin.register(Deal)
class DealAdmin(SimpleHistoryAdmin):
    list_display = ['title', 'bitrix_id', 'pipeline', 'stage', 'amount', 'is_closed', 'created_at', 'last_sync', 'view_history_link']
    list_display = ['title', 'bitrix_id', 'pipeline', 'stage', 'amount', 'company', 'region', 'created_at', 'last_sync', 'view_history_link']
    list_filter = ('pipeline', 'stage', 'is_closed', 'created_at')
    search_fields = ('title', 'bitrix_id')
    readonly_fields = ('bitrix_id', 'created_at', 'closed_at', 'last_sync', 'details_pretty', 'view_history_link')
    fieldsets = (
        ('Основная информация', {
            'fields': ('bitrix_id', 'title', 'pipeline', 'stage', 'program', 'company','region', 'amount', 'is_closed', 'is_new')
        }),
        ('Даты', {
            'fields': ('created_at', 'closed_at', 'last_sync')
        }),
        ('История', {
            'fields': ('view_history_link',)
        }),
        ('Детали', {
            'fields': ('details_pretty',),
        }),
    )
    
    def view_history_link(self, obj):
        """Ссылка на просмотр истории"""
        if obj.pk:
            url = reverse('crm_connector:object_history', args=['deal', obj.pk])
            return format_html('<a href="{}" target="_blank">Просмотреть историю изменений</a>', url)
        return '-'
    view_history_link.short_description = 'История'
    
    def details_pretty(self, obj):
        """Отображает детали сделки в читаемом формате"""
        if not obj.details:
            return "Нет данных"
        from django.utils.safestring import mark_safe
        import json
        formatted_json = json.dumps(obj.details, ensure_ascii=False, indent=2)
        return mark_safe(f'<pre>{formatted_json}</pre>')
    
    details_pretty.short_description = 'Детали сделки'

admin.site.register(Lead, admin.ModelAdmin)

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ['title', 'bitrix_id']
    search_fields = ['title', 'bitrix_id']

@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ('name', 'last_name', 'phone', 'email', 'bitrix_id')
    search_fields = ('name', 'last_name', 'phone', 'email')
    list_filter = ('created_at',)

@admin.register(AtlasProgram)
class AtlasProgramAdmin(admin.ModelAdmin):
    list_display = ['program_id', 'title', 'short_title']
    search_fields = ['program_id', 'title', 'short_title']
    readonly_fields = ['section', 'topics']

@admin.register(AtlasApplication)
class AtlasApplicationAdmin(SimpleHistoryAdmin):
    list_display = ['application_id', 'full_name', 'phone', 'email', 'region', 'deal_link', 'is_synced', 'last_sync', 'history_link']
    list_filter = ['is_synced', 'region', 'created_at', 'last_sync']
    search_fields = ['application_id', 'full_name', 'phone', 'email']
    readonly_fields = ['created_at', 'updated_at', 'last_sync', 'raw_data_formatted', 'history_link', 'JSON_ed_progress', 'generated_application_link', 'signed_application_link']
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('application_id', 'full_name', 'phone', 'email', 'region', 'postal_code', 'JSON_ed_progress')
        }),
        ('Связь с Битрикс24', {
            'fields': ('deal', 'is_synced', 'sync_errors')
        }),
        ('История', {
            'fields': ('history_link',)
        }),
        ('Исходные данные', {
            'fields': ('raw_data_formatted',),
            'classes': ('collapse',)
        }),
        ('Файлы', {
            'fields': ('generated_application_link', 'signed_application_link')
        }),
        ('Системная информация', {
            'fields': ('created_at', 'updated_at', 'last_sync')
        })
    )
    
    def history_link(self, obj):
        """Ссылка на просмотр истории"""
        if obj.pk:
            url = reverse('crm_connector:object_history', args=['atlasapplication', obj.pk])
            return format_html('<a href="{}" target="_blank">Просмотреть историю</a>', url)
        return '-'
    history_link.short_description = 'История'
    
    def deal_link(self, obj):
        """Ссылка на связанную сделку"""
        if obj.deal:
            url = reverse('admin:crm_connector_deal_change', args=[obj.deal.id])
            return format_html('<a href="{}">{}</a>', url, obj.deal.title)
        return '-'
    deal_link.short_description = 'Сделка'
    
    def raw_data_formatted(self, obj):
        """Форматированный вывод JSON данных"""
        import json
        if obj.raw_data:
            formatted = json.dumps(obj.raw_data, indent=2, ensure_ascii=False)
            return format_html('<pre style="white-space: pre-wrap;">{}</pre>', formatted)
        return '-'
    raw_data_formatted.short_description = 'Исходные данные'
    
    def generated_application_link(self, obj):
        """Ссылка на сгенерированное заявление"""
        if obj.generated_application:
            url = obj.generated_application.url
            filename = obj.generated_application.name.split('/')[-1]
            return format_html('<a href="{}" target="_blank">📄 {}</a>', url, filename)
        return '-'
    generated_application_link.short_description = 'Сгенерированное заявление'
    
    def signed_application_link(self, obj):
        """Ссылка на подписанное заявление"""
        if obj.signed_application:
            url = obj.signed_application.url
            filename = obj.signed_application.name.split('/')[-1]
            return format_html('<a href="{}" target="_blank">✍️ {}</a>', url, filename)
        return '-'
    signed_application_link.short_description = 'Подписанное заявление'
    
    actions = ['sync_with_bitrix', 'mark_as_synced']
    
    def sync_with_bitrix(self, request, queryset):
        """Синхронизировать выбранные заявки с Битрикс24"""
        # TODO: Реализовать синхронизацию
        self.message_user(request, f"Функция синхронизации в разработке")
    sync_with_bitrix.short_description = "Синхронизировать с Битрикс24"
    
    def mark_as_synced(self, request, queryset):
        """Отметить как синхронизированные"""
        updated = queryset.update(is_synced=True, last_sync=timezone.now())
        self.message_user(request, f"Отмечено как синхронизированные: {updated} заявок")
    mark_as_synced.short_description = "Отметить как синхронизированные"

@admin.register(AtlasStatus)
class AtlasStatusAdmin(admin.ModelAdmin):
    list_display = ['name', 'order', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name']
    ordering = ['order', 'name']

@admin.register(RRStatus)
class RRStatusAdmin(admin.ModelAdmin):
    list_display = ['name', 'order', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name']
    ordering = ['order', 'name']

@admin.register(StageRule)
class StageRuleAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'pipeline', 'target_stage', 'priority', 'is_active']
    list_filter = ['pipeline', 'is_active', 'target_stage']
    search_fields = ['description', 'atlas_status__name', 'rr_status__name']
    ordering = ['priority', 'id']
    
    fieldsets = (
        ('Основные настройки', {
            'fields': ('pipeline', 'target_stage', 'priority', 'is_active')
        }),
        ('Условия', {
            'fields': ('atlas_status', 'rr_status'),
            'description': 'Укажите один или оба статуса. Правило сработает, если все указанные статусы совпадут.'
        }),
        ('Дополнительно', {
            'fields': ('description',),
            'classes': ('collapse',)
        }),
    )
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Фильтруем стадии по выбранной воронке"""
        if db_field.name == "target_stage":
            if request.resolver_match.kwargs.get('object_id'):
                # При редактировании существующего правила
                try:
                    rule = StageRule.objects.get(pk=request.resolver_match.kwargs['object_id'])
                    kwargs["queryset"] = Stage.objects.filter(pipeline=rule.pipeline)
                except StageRule.DoesNotExist:
                    pass
        return super().formfield_for_foreignkey(db_field, request, **kwargs) 