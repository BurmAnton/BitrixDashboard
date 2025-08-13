from django import forms
from .models import Deal
from .bitrix24_api import Bitrix24API

class ExcelImportForm(forms.Form):
    excel_file = forms.FileField(
        label='Excel файл',
        help_text='Выберите файл Excel для импорта'
    )
    
    pipeline_name = forms.CharField(
        label='Название воронки',
        max_length=255,
        initial='Заявки (граждане)',
        help_text='Укажите название воронки в Битрикс24 для импорта заявок',
        required=False
    )
    
    # Динамические поля - будут заполнены в __init__
    business_sphere = forms.ChoiceField(
        label='Сфера деятельности',
        help_text='Выберите сферу деятельности для всех организаций'
    )
    
    organization_type = forms.ChoiceField(
        label='Тип организации',
        help_text='Выберите тип организации для всех организаций'
    )
    
    def __init__(self, *args, **kwargs):
        # Извлекаем дополнительные параметры
        industries = kwargs.pop('industries', [])
        company_types = kwargs.pop('company_types', [])
        
        super().__init__(*args, **kwargs)
        
        # Формируем choices для полей на основе переданных данных
        if industries:
            self.fields['business_sphere'].choices = [('', '-- Выберите --')] + [
                (ind[0], ind[1]) for ind in industries
            ]
        else:
            # Значения по умолчанию
            self.fields['business_sphere'].choices = [
                ('', '-- Выберите --'),
                ('IT', 'Информационные технологии'),
                ('MANUFACTURING', 'Производство'),
                ('TRADE', 'Торговля'),
                ('SERVICES', 'Услуги'),
                ('OTHER', 'Другое')
            ]
            
        if company_types:
            self.fields['organization_type'].choices = [('', '-- Выберите --')] + [
                (ct[0], ct[1]) for ct in company_types
            ]
        else:
            # Значения по умолчанию
            self.fields['organization_type'].choices = [
                ('', '-- Выберите --'),
                ('CUSTOMER', 'Клиент'),
                ('PARTNER', 'Партнер'),
                ('COMPETITOR', 'Конкурент'),
                ('OTHER', 'Другое')
            ]
    
    def clean_excel_file(self):
        excel_file = self.cleaned_data.get('excel_file')
        if excel_file:
            file_extension = excel_file.name.split('.')[-1]
            if file_extension.lower() not in ['xlsx', 'xls']:
                raise forms.ValidationError('Загрузите корректный файл Excel (.xlsx или .xls)')
        return excel_file 

api = Bitrix24API()
class LeadImportForm(forms.Form):
    excel_file = forms.FileField(label='Выберите Excel файл с лидами')
    training = forms.ChoiceField(
        label='Направление обучения',
        choices=api.get_deal_field_list('UF_CRM_1741091080288'),
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    

# ------------------------------------------------------------------
# Форма для проверки стадии сделки по статусам Атлас/РР
# ------------------------------------------------------------------


class StageCheckForm(forms.Form):
    atlas_status = forms.CharField(
        label='Статус в Атлас',
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Например: Заявка принята'})
    )
    rr_status = forms.CharField(
        label='Статус в РР',
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Например: Допущен'})
    ) 