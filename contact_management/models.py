from django.core.exceptions import ValidationError
from django.db import models
from simple_history.models import HistoricalRecords

from education_planner.models import ProfActivity, ROIV

class FederalDistrict(models.Model):
    """Модель для хранения федеральный округов"""
    name = models.CharField('Название округа', max_length=255, unique=True)
    
    class Meta:
        verbose_name = 'Федеральный округ'
        verbose_name_plural = 'Федеральные округа'
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
class Region(models.Model):
    """Модель для хранения регионов реализации программ"""
    name = models.CharField('Название региона', max_length=255, unique=True)
    code = models.CharField('Код региона', max_length=10, blank=True, help_text='Числовой код региона')
    federalDistrict = models.ForeignKey(FederalDistrict, on_delete=models.SET_NULL, null=True, blank=True, related_name="region", verbose_name="Округ")
    is_active = models.BooleanField('Активен', default=True)
    created_at = models.DateTimeField('Дата создания', auto_now_add=True)
    updated_at = models.DateTimeField('Дата обновления', auto_now=True)
    
    class Meta:
        verbose_name = 'Регион'
        verbose_name_plural = 'Регионы'
        ordering = ['name']
    
    def __str__(self):
        return self.name

class OrganizationType(models.Model):
    """Модель для хранения типов организаций"""
    name = models.CharField(max_length=255)

    class Meta:
        verbose_name = 'тип организации'
        verbose_name_plural = 'Типы организации'
        
    def __str__(self):
        return self.name

class Organization(models.Model):
    """Модель для хранения организаций"""
    name = models.CharField(max_length=500,verbose_name='Название организации',blank=True,null=True)
    full_name = models.CharField(blank=True,verbose_name='Полное наименование',)
    inn = models.CharField(verbose_name="ИНН", unique=True)
    type = models.ForeignKey(OrganizationType,on_delete=models.SET_NULL,related_name="organization",verbose_name="Тип организации",null=True,blank=True)
    roiv = models.ForeignKey(ROIV,on_delete=models.SET_NULL,related_name="organization",verbose_name="Данные РОИВ",null=True,blank=True)
    region = models.ForeignKey(Region,on_delete=models.SET_NULL,related_name='organization',verbose_name='Регион',blank=True,null=True)
    federal_company = models.BooleanField(default=False,verbose_name="Федеральная")
    is_our_side = models.BooleanField(default=False, verbose_name="Наша организация")
    prof_activity = models.ManyToManyField(ProfActivity,related_name='organization',verbose_name='Сфера деятельности',blank=True,)
    is_active = models.BooleanField(default=True,verbose_name='Активен')
    parent_company = models.ForeignKey('self',on_delete=models.SET_NULL,blank=True,null=True,related_name="child",)
    created_at = models.DateTimeField(auto_now_add=True,verbose_name='Дата создания')
    updated_at = models.DateTimeField(auto_now=True,verbose_name='Дата обновления')

    # projects — обратная M2M с модели Projects; simple_history ожидает прямое M2M на Organization — только prof_activity
    history = HistoricalRecords(m2m_fields=("prof_activity",))

    class Meta:
        verbose_name = 'Организация'
        verbose_name_plural = 'Организации'
    
    def __str__(self):
        return f'{self.name}'
    
    def save(self, *args, **kwargs):
        # Заполняем поля из ROIV, только если объект создаётся (id ещё нет)
        if self.pk is None and self.roiv is not None:
            self.name = self.roiv.name
            self.full_name = self.roiv.full_name
            self.is_active = self.roiv.is_active

        super().save(*args, **kwargs)

class Contact(models.Model):
    """Модель для хранения контактов организаций"""
    type = models.CharField(choices=[("department","Отдел"), ("person","Сотрудник"), ("main", "Основной"), ("other", "Другой")], verbose_name="Тип контакта")
    department_name = models.CharField(max_length=255, blank=True, null=True, verbose_name="Название отдела")

    first_name = models.CharField(max_length=255, blank=True, null=True, verbose_name="Имя")
    last_name = models.CharField(max_length=255, blank=True, null=True, verbose_name="Фамилия")
    middle_name = models.CharField(max_length=255, blank=True, null=True, verbose_name="Отчество")
    first_name_dat = models.CharField(max_length=255, blank=True, null=True, verbose_name="Имя в дательном падеже")
    last_name_dat = models.CharField(max_length=255, blank=True, null=True, verbose_name="Фамилия в дательном падеже")
    middle_name_dat = models.CharField(max_length=255, blank=True, null=True, verbose_name="Отчество в дательном падеже")

    position = models.CharField(max_length=255, blank=True, null=True, verbose_name="Должность")
    position_dat = models.CharField(max_length=255, blank=True, null=True, verbose_name="Должность в дательном падеже")
    manager = models.BooleanField(default=False, verbose_name="Руководитель организации")

    comment = models.TextField(blank=True, verbose_name="Комментарий")
    current = models.BooleanField(default=True, verbose_name="Актуальный")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="contacts", verbose_name="Организация")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name = 'Контакт'
        verbose_name_plural = 'Контакты'
        
    def __str__(self):
        return f"{self.organization} ({self.comment or 'без комментария'})"

class ContactPhone(models.Model):
    contact = models.ForeignKey(Contact,on_delete=models.CASCADE,related_name="phones",verbose_name="Контакт",)
    number = models.CharField("Телефон", max_length=30)
    comment = models.CharField(blank=True, verbose_name="Комментарий")
    is_active = models.BooleanField("Актуальный", default=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Телефон"
        verbose_name_plural = "Телефоны"

    def __str__(self):
        return f"{self.number} ({self.comment or 'без комментария'})"

class ContactEmail(models.Model):
    contact = models.ForeignKey(Contact,on_delete=models.CASCADE,related_name="emails",verbose_name="Контакт",)
    email = models.EmailField("Email")
    comment = models.CharField(blank=True, verbose_name="Комментарий")
    is_active = models.BooleanField("Актуальный", default=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Email"
        verbose_name_plural = "Email‑адреса"

    def __str__(self):
        return f"{self.email} ({self.comment or 'без комментария'})"
    
class HistoryOrganization(models.Model):
    """Модель для хранения истории изменений организации"""
    organization = models.ForeignKey(Organization,on_delete=models.CASCADE, related_name="legacy_history", verbose_name="Организация")
    name = models.CharField("Название", max_length=255, blank=True, null=True)
    status = models.CharField(choices=[('active','Активный'),('closed','Закрыто'),('integrated','Интегрировано')], verbose_name="Статус")
    integrated_to = models.ForeignKey(Organization, on_delete=models.SET_NULL, related_name="integrated", blank=True, null=True, verbose_name="Интегрировано в")
    date = models.DateTimeField("Дата изменений", blank=True, null=True)
    priority = models.BooleanField("Приоритет", default=True)

    class Meta:
        verbose_name = "запись"
        verbose_name_plural = "История изменений организации"

    def __str__(self):
        return str(self.name)
    
class Projects(models.Model):
    """Модель для хранения проектов"""
    name = models.CharField(max_length=255, blank=True, null=True, verbose_name="Название")
    organizations= models.ManyToManyField(
        Organization,
        related_name='projects',
        verbose_name='Организации',
        blank=True,
    )

    class Meta:
        verbose_name = "проект"
        verbose_name_plural = "Проекты"

    def __str__(self):
        return str(self.name)


class CommunicationInteraction(models.Model):
    class Channel(models.TextChoices):
        EMAIL = "email", "Email"
        POSTAL_MAIL = "postal_mail", "Почта"
        LETTER = "letter", "Письмо"
        MESSENGER = "messenger", "Мессенджер"
        MEETING = "meeting", "Встреча"
        CALL = "call", "Созвон"
        PHONE = "phone", "Телефон"

    counterparty_organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="communication_interactions",
        verbose_name="Контрагент (организация)",
    )
    counterparty_contact = models.ForeignKey(
        Contact,
        on_delete=models.SET_NULL,
        related_name="communication_interactions",
        verbose_name="Контрагент (контакт)",
        null=True,
        blank=True,
    )
    our_organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="our_communication_interactions",
        verbose_name="Наша организация",
    )
    channel = models.CharField(
        max_length=20,
        choices=Channel.choices,
        verbose_name="Канал коммуникации",
    )
    occurred_at = models.DateTimeField(verbose_name="Дата и время коммуникации")
    result = models.TextField(verbose_name="Результат коммуникации")
    project = models.ForeignKey(
        Projects,
        on_delete=models.SET_NULL,
        related_name="communication_interactions",
        verbose_name="Проект",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата изменения")

    class Meta:
        verbose_name = "коммуникация"
        verbose_name_plural = "Журнал коммуникаций"
        ordering = ("-occurred_at", "-id")

    def clean(self):
        if (
            self.counterparty_contact_id
            and self.counterparty_contact.organization_id != self.counterparty_organization_id
        ):
            raise ValidationError(
                {"counterparty_contact": "Контакт должен принадлежать выбранной организации-контрагенту."}
            )
        if self.our_organization_id and not self.our_organization.is_our_side:
            raise ValidationError({"our_organization": "Выберите организацию, отмеченную как 'Наша организация'."})

    def __str__(self):
        cp = self.counterparty_organization.name or self.counterparty_organization.inn
        return f"{self.get_channel_display()} -> {cp} ({self.occurred_at:%Y-%m-%d %H:%M})"