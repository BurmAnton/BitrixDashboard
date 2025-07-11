from django.contrib import admin
from .models import ProfActivity, EducationProgram, ProgramSection

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
