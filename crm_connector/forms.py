from django import forms
from .models import Deal, REGION_CHOICES
from .bitrix24_api import Bitrix24API
from django.core.validators import MinValueValidator, MaxValueValidator
from dal import autocomplete

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
    

class AtlasLeadImportForm(forms.Form):
    excel_file = forms.FileField(label='Выберите Excel файл с заявками')
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


class DocumentForm(forms.Form):
    snils = forms.IntegerField(
        label="СНИЛС",
        validators=[
            MinValueValidator(1000000000, message="Не верный формат СНИЛС"),
            MaxValueValidator(99999999999, message="Не верный формат СНИЛС")
        ],
        widget=forms.TextInput(attrs={'placeholder': 'Укажите Ваш СНИЛС',"inputmode": "numeric", 'class': 'form-control form-control-sm', "maxlength": 11})
    )
    postal_code = forms.IntegerField(
        label="Почтовый индекс",
        validators=[
            MinValueValidator(100000, message="Не верный формат почтового индекса"),
            MaxValueValidator(999999, message="Не верный формат почтового индекса")
        ],
        widget=forms.TextInput(attrs={'placeholder': '445051',"inputmode": "numeric", 'class': 'form-control form-control-sm', "maxlength": 6})
    )
    region = forms.ChoiceField(
        label="Регион",
        choices=[('', '-- Выберите регион --')] + list(REGION_CHOICES),
        widget=forms.Select(attrs={
            'class': 'form-control form-control-sm select2',
            'style': 'width: 100%',
            'data-placeholder': 'Начните вводить название региона...',
            'data-allow-clear': 'true'
        })
    )
    settlement = forms.CharField(
        label="Населенный пункт",
        widget=forms.TextInput(attrs={'placeholder': 'Город, село, деревня...', 'class': 'form-control form-control-sm'})
    )
    street = forms.CharField(
        label="Улица/другое",
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Улица, проспект, переулок...', 'class': 'form-control form-control-sm'})
    )
    house = forms.CharField(
        label="Дом/другое",
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Номер дома', 'class': 'form-control form-control-sm'})
    )
    building = forms.CharField(
        label="Корпус/другое",
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Корпус, строение...', 'class': 'form-control form-control-sm'})
    )
    apartment = forms.CharField(
        label="Квартира/другое",
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Номер квартиры', 'class': 'form-control form-control-sm'})
    )


class SignedApplicationForm(forms.Form):
    snils = forms.IntegerField(
        label="СНИЛС",
        validators=[
            MinValueValidator(1000000000, message="Не верный формат СНИЛС"),
            MaxValueValidator(99999999999, message="Не верный формат СНИЛС")
        ],
        widget=forms.TextInput(attrs={'placeholder': 'Укажите Ваш СНИЛС',"inputmode": "numeric", 'class': 'form-control form-control-sm', "maxlength": 11})
    )
    signed_application = forms.FileField(
        label="Подписанное заявление",
        help_text="Загрузите скан или фото подписанного заявления",
        widget=forms.FileInput(attrs={'class': 'form-control form-control-sm', 'accept': '.pdf,.jpg,.jpeg,.png'})
    )
