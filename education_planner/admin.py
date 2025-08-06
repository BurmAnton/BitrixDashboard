from django.contrib import admin
from .models import (
    ProfActivity, EducationProgram, ProgramSection,
    EduAgreement, Quota, Supplement, QuotaChange, Region
)

@admin.register(ProfActivity)
class ProfActivityAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at', 'updated_at')
    search_fields = ('name', 'description')
    list_filter = ('created_at', 'updated_at')

@admin.register(EducationProgram)
class EducationProgramAdmin(admin.ModelAdmin):
    list_display = ('name', 'program_type', 'study_form', 'academic_hours', 'created_at')
    list_filter = ('program_type', 'study_form', 'activities', 'created_at')
    search_fields = ('name', 'description')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(ProgramSection)
class ProgramSectionAdmin(admin.ModelAdmin):
    list_display = ('name', 'program', 'order', 'created_at')
    list_filter = ('program', 'created_at')
    search_fields = ('name', 'description', 'program__name')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'code')
    readonly_fields = ('created_at', 'updated_at')


# Inline для квот в договоре
class QuotaInline(admin.TabularInline):
    model = Quota
    extra = 1
    fields = ('education_program', 'regions', 'quantity', 'cost_per_quota', 'start_date', 'end_date', 'is_active')
    readonly_fields = ('created_at', 'updated_at')
    filter_horizontal = ('regions',)


# Inline для допсоглашений в договоре
class SupplementInline(admin.TabularInline):
    model = Supplement
    extra = 0
    fields = ('number', 'signing_date', 'status', 'description', 'document_link')
    readonly_fields = ('created_at', 'updated_at')
    show_change_link = True


@admin.register(EduAgreement)
class EduAgreementAdmin(admin.ModelAdmin):
    list_display = ('number', 'name', 'federal_operator', 'status', 'signing_date', 'created_at')
    list_filter = ('federal_operator', 'status', 'signing_date', 'created_at')
    search_fields = ('number', 'name', 'notes')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [QuotaInline, SupplementInline]
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('federal_operator', 'name', 'number', 'signing_date', 'status')
        }),
        ('Документы', {
            'fields': ('document_link',)
        }),
        ('Дополнительно', {
            'fields': ('notes', 'created_at', 'updated_at')
        }),
    )


@admin.register(Quota)
class QuotaAdmin(admin.ModelAdmin):
    list_display = ('agreement', 'education_program', 'regions_display', 'quantity', 'cost_per_quota', 'formatted_start_date', 'formatted_end_date', 'is_active', 'created_at')
    list_filter = ('agreement', 'education_program', 'regions', 'is_active', 'start_date', 'end_date', 'created_at')
    search_fields = ('agreement__number', 'agreement__name', 'education_program__name', 'regions__name')
    readonly_fields = ('created_at', 'updated_at', 'formatted_total_cost', 'formatted_start_date', 'formatted_end_date', 'duration_days')
    filter_horizontal = ('regions',)
    fieldsets = (
        ('Основная информация', {
            'fields': ('agreement', 'education_program', 'regions', 'quantity', 'cost_per_quota')
        }),
        ('Период обучения', {
            'fields': ('start_date', 'end_date'),
        }),
        ('Статистика', {
            'fields': ('formatted_total_cost', 'formatted_start_date', 'formatted_end_date', 'duration_days'),
            'classes': ('collapse',)
        }),
        ('Управление', {
            'fields': ('is_active',)
        }),
        ('Системная информация', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('agreement', 'education_program').prefetch_related('regions')


# Inline для изменений квот в допсоглашении
class QuotaChangeInline(admin.TabularInline):
    model = QuotaChange
    extra = 1
    fields = ('change_type', 'education_program', 'region', 'old_quantity', 'new_quantity', 'comment')
    readonly_fields = ('created_at',)


@admin.register(Supplement)
class SupplementAdmin(admin.ModelAdmin):
    list_display = ('number', 'agreement', 'status', 'signing_date', 'created_at')
    list_filter = ('status', 'signing_date', 'created_at', 'agreement')
    search_fields = ('number', 'agreement__number', 'agreement__name', 'description')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [QuotaChangeInline]
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('agreement', 'number', 'signing_date', 'status')
        }),
        ('Описание изменений', {
            'fields': ('description',)
        }),
        ('Документы', {
            'fields': ('document_link',)
        }),
        ('Системная информация', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(QuotaChange)
class QuotaChangeAdmin(admin.ModelAdmin):
    list_display = ('supplement', 'change_type', 'education_program', 'region', 'old_quantity', 'new_quantity', 'created_at')
    list_filter = ('change_type', 'supplement__agreement', 'education_program', 'created_at')
    search_fields = ('supplement__number', 'education_program__name', 'region', 'comment')
    readonly_fields = ('created_at',)
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('supplement', 'supplement__agreement', 'education_program')
