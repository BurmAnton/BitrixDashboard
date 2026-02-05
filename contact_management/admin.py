from django.contrib import admin
from .models import (
    HistoryOrganization,
    OrganizationType,
    FederalDistrict,
    Organization,
    ContactPhone,
    ContactEmail,
    Projects,
    Contact,
    Region
)

@admin.register(FederalDistrict)
class FederalDistrictAdmin(admin.ModelAdmin):
    list_display = ("name",)

@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "federalDistrict__name")
    list_filter = ("federalDistrict__name",)

@admin.register(OrganizationType)
class OrganizationTypeAdmin(admin.ModelAdmin):
    list_display = ("name",)


class PhoneInline(admin.TabularInline):
    model = ContactPhone
    extra = 1
    fields = ("number", "comment", "is_active")


class EmailInline(admin.TabularInline):
    model = ContactEmail
    extra = 1
    fields = ("email", "comment", "is_active")


class ContactInline(admin.StackedInline):
    model = Contact
    extra = 1
    fields = (
        "type",
        "department_name",
        "first_name",
        "last_name",
        "middle_name",
        "position",
        "manager",
        "comment",
        "current",
    )
    inlines = [PhoneInline, EmailInline]


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "type",
        "region",
        "federal_company",
        "is_active",
        "get_prof_activities",
    )
    list_filter = (
        "type",
        "region",
        "federal_company",
        "is_active",
    )
    search_fields = (
        "name",
        "full_name",
        "region__name",
        "prof_activity__name",
        "history__name"
    )
    filter_horizontal = ("prof_activity",)
    inlines = [ContactInline]

    def get_prof_activities(self, obj):
        return ", ".join(pa.name for pa in obj.prof_activity.all())

    get_prof_activities.short_description = "Сфера деятельности"


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = (
        "organization",
        "type",
        "get_full_name",
        "position",
        "manager",
        "current",
    )
    list_filter = (
        "type",
        "manager",
        "current",
        "organization__type",
        "organization__region",
    )
    search_fields = (
        "organization__name",
        "first_name",
        "last_name",
        "middle_name",
        "department_name",
        "position",
    )
    inlines = [PhoneInline, EmailInline]

    def get_full_name(self, obj):
        parts = [obj.first_name, obj.last_name, obj.middle_name]
        return " ".join(filter(None, parts)) or "—"

    get_full_name.short_description = "ФИО"


@admin.register(HistoryOrganization)
class HistoryOrganizationAdmin(admin.ModelAdmin):
    list_display = ('name', 'status', 'date', 'priority')
    list_filter = ('date', 'organization')
    search_fields = ('organization', 'name')

    
@admin.register(Projects)
class ProjectsAdmin(admin.ModelAdmin):
    list_display = ('name', )
    search_fields = ('name',)
    filter_horizontal = ("organizations",)