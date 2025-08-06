from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.core.exceptions import ValidationError

class ProfActivity(models.Model):
    """Модель для хранения сфер деятельности"""
    name = models.CharField(_('Название сферы'), max_length=255)
    description = models.TextField(_('Описание сферы деятельности'), blank=True)
    created_at = models.DateTimeField(_('Дата создания'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Дата обновления'), auto_now=True)

    class Meta:
        verbose_name = _('Сфера деятельности')
        verbose_name_plural = _('Сферы деятельности')
        ordering = ['name']

    def __str__(self):
        return self.name

class EducationProgram(models.Model):
    """Модель для хранения образовательных программ"""
    
    class ProgramType(models.TextChoices):
        ADVANCED = 'ADV', _('ДПО ПК')
        PROFESSIONAL_RE = 'PROFP', _('ПО ПП')
        PROFESSIONAL = 'PROF', _('ПО')

    class StudyForm(models.TextChoices):
        FULL_TIME = 'FT', _('Очная')
        PART_TIME = 'PT', _('Очно-заочная')
        DISTANCE = 'DIST', _('Заочная')
    
    name = models.CharField(_('Название программы'), max_length=255)
    academic_hours = models.PositiveIntegerField(_('Длительность (ак. часы)'), default=0)
    program_type = models.CharField(
        _('Вид программы'),
        max_length=5,
        choices=ProgramType.choices,
        default=ProgramType.PROFESSIONAL
    )
    study_form = models.CharField(
        _('Форма обучения'),
        max_length=5,
        choices=StudyForm.choices,
        default=StudyForm.FULL_TIME
    )
    activities = models.ForeignKey(
        ProfActivity,
        verbose_name=_('Сфера деятельности'),
        related_name='education_programs',
        on_delete=models.CASCADE,
        blank=True,
        null=True
    )
    description = models.TextField(_('Описание программы'), blank=True)
    duration = models.PositiveIntegerField(_('Длительность (часов)'), default=0)
    final_attestation = models.PositiveIntegerField(_('Длительность итоговой аттестации (ак. часы)'), default=0)
    created_at = models.DateTimeField(_('Дата создания'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Дата обновления'), auto_now=True)

    class Meta:
        verbose_name = _('Образовательная программа')
        verbose_name_plural = _('Образовательные программы')
        ordering = ['name']

    def __str__(self):
        return self.name

class ProgramSection(models.Model):
    """Модель для хранения разделов образовательной программы"""
    program = models.ForeignKey(
        EducationProgram,
        verbose_name=_('Образовательная программа'),
        on_delete=models.CASCADE,
        related_name='sections'
    )
    name = models.CharField(_('Название раздела'), max_length=255)
    lecture_hours = models.PositiveIntegerField(_('Лекции (Л)'), default=0)
    practice_hours = models.PositiveIntegerField(_('Практические занятия (ПЗ)'), default=0)
    selfstudy_hours = models.PositiveIntegerField(_('Самостоятельная работа (СР)'), default=0)
    workload = models.PositiveIntegerField(_('Трудоёмкость (часы)'), default=0)
    attestation_form = models.CharField(_('Форма аттестации'), max_length=255, blank=True)
    description = models.TextField(_('Описание раздела'), blank=True)
    order = models.PositiveIntegerField(_('Порядок'), default=0)
    created_at = models.DateTimeField(_('Дата создания'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Дата обновления'), auto_now=True)

    class Meta:
        verbose_name = _('Раздел программы')
        verbose_name_plural = _('Разделы программы')
        ordering = ['order', 'name']
        unique_together = ['program', 'order']

    def __str__(self):
        return f"{self.program.name} - {self.name}"


class Region(models.Model):
    """Модель для хранения регионов реализации программ"""
    name = models.CharField(_('Название региона'), max_length=255, unique=True)
    code = models.CharField(_('Код региона'), max_length=10, blank=True, help_text=_('Числовой код региона'))
    is_active = models.BooleanField(_('Активен'), default=True)
    created_at = models.DateTimeField(_('Дата создания'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Дата обновления'), auto_now=True)
    
    class Meta:
        verbose_name = _('Регион')
        verbose_name_plural = _('Регионы')
        ordering = ['name']
    
    def __str__(self):
        return self.name


class EduAgreement(models.Model):
    """Модель для хранения договоров на обучение с федеральными операторами"""
    
    class FederalOperator(models.TextChoices):
        IRPO = 'IRPO', _('ИРПО')
        VNII = 'VNII', _('ВНИИ')
    
    class AgreementStatus(models.TextChoices):
        NEGOTIATION = 'NEGOTIATION', _('На согласовании')
        SIGNING = 'SIGNING', _('На подписании')
        SIGNED = 'SIGNED', _('Подписан')
        COMPLETED = 'COMPLETED', _('Выполнен')
    
    federal_operator = models.CharField(
        _('Федеральный оператор'),
        max_length=4,
        choices=FederalOperator.choices,
        default=FederalOperator.IRPO
    )
    name = models.CharField(_('Название договора'), max_length=500)
    number = models.CharField(_('Номер договора'), max_length=100, unique=True)
    signing_date = models.DateField(_('Дата подписания'), null=True, blank=True)
    status = models.CharField(
        _('Статус'),
        max_length=20,
        choices=AgreementStatus.choices,
        default=AgreementStatus.NEGOTIATION
    )
    document_link = models.URLField(_('Ссылка на договор'), blank=True)
    notes = models.TextField(_('Примечания'), blank=True)
    created_at = models.DateTimeField(_('Дата создания'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Дата обновления'), auto_now=True)
    
    class Meta:
        verbose_name = _('Договор на обучение')
        verbose_name_plural = _('Договоры на обучение')
        ordering = ['-signing_date', '-created_at']
    
    def __str__(self):
        return f"{self.get_federal_operator_display()} - {self.number} от {self.signing_date or 'не подписан'}"
    
    def get_actual_quotas(self):
        """Возвращает актуальные квоты с учетом дополнительных соглашений"""
        # Если есть активные дополнительные соглашения, используем квоты из последнего
        active_supplements = self.supplements.exclude(
            status=Supplement.SupplementStatus.DRAFT
        ).order_by('-signing_date', '-created_at')
        
        if active_supplements.exists():
            # Используем квоты из последнего дополнительного соглашения
            # Квоты создаются при импорте и деактивируются старые
            return self.quotas.filter(is_active=True).select_related('education_program').prefetch_related('regions')
        else:
            # Возвращаем базовые квоты
            return self.quotas.filter(is_active=True).select_related('education_program').prefetch_related('regions')
    
    def get_total_quota_places(self):
        """Возвращает общее количество мест по всем квотам"""
        return sum(getattr(quota, 'actual_quantity', quota.quantity) for quota in self.get_actual_quotas())
    
    def get_total_agreement_cost(self):
        """Возвращает общую стоимость всех квот по договору"""
        return sum(quota.total_cost for quota in self.get_actual_quotas())
    
    def get_formatted_total_cost(self):
        """Возвращает отформатированную общую стоимость договора"""
        return f"{self.get_total_agreement_cost():,.2f} ₽"


class Quota(models.Model):
    """Модель для хранения квот по договорам"""
    
    agreement = models.ForeignKey(
        EduAgreement,
        verbose_name=_('Договор'),
        on_delete=models.CASCADE,
        related_name='quotas'
    )
    education_program = models.ForeignKey(
        EducationProgram,
        verbose_name=_('Программа обучения'),
        on_delete=models.PROTECT,
        related_name='quotas'
    )
    regions = models.ManyToManyField(
        Region,
        verbose_name=_('Регионы реализации'),
        related_name='quotas',
        help_text=_('Выберите один или несколько регионов')
    )
    # Оставляем старое поле для совместимости, но делаем его необязательным
    region = models.CharField(_('Регион (устаревшее)'), max_length=255, blank=True, null=True)
    quantity = models.PositiveIntegerField(_('Количество квоты'), default=0)
    cost_per_quota = models.DecimalField(
        _('Стоимость за заявку'),
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text=_('Стоимость обучения одного человека по данной квоте')
    )
    start_date = models.DateField(
        _('Дата начала обучения'),
        null=True,
        blank=True,
        help_text=_('Планируемая дата начала обучения по данной квоте')
    )
    end_date = models.DateField(
        _('Дата окончания обучения'),
        null=True,
        blank=True,
        help_text=_('Планируемая дата окончания обучения по данной квоте')
    )
    is_active = models.BooleanField(_('Активна'), default=True)
    created_at = models.DateTimeField(_('Дата создания'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Дата обновления'), auto_now=True)
    
    class Meta:
        verbose_name = _('Квота')
        verbose_name_plural = _('Квоты')
        ordering = ['agreement', 'education_program']
    
    def __str__(self):
        regions_str = ", ".join([r.name for r in self.regions.all()]) if self.regions.exists() else self.region or "Не указан"
        return f"{self.education_program.name} - {regions_str} ({self.quantity} мест)"
    
    @property
    def regions_display(self):
        """Возвращает строку с названиями регионов с новой строки"""
        if self.regions.exists():
            return "\n".join([r.name for r in self.regions.all()])
        return self.region or "Не указан"
    
    @property
    def total_cost(self):
        """Возвращает общую стоимость квоты (количество * стоимость за заявку)"""
        return self.quantity * self.cost_per_quota
    
    @property
    def formatted_cost_per_quota(self):
        """Возвращает отформатированную стоимость за заявку"""
        return f"{self.cost_per_quota:,.2f} ₽"
    
    @property
    def formatted_total_cost(self):
        """Возвращает отформатированную общую стоимость"""
        return f"{self.total_cost:,.2f} ₽"
    
    @property
    def formatted_start_date(self):
        """Возвращает отформатированную дату начала"""
        return self.start_date.strftime('%d.%m.%Y') if self.start_date else '—'
    
    @property
    def formatted_end_date(self):
        """Возвращает отформатированную дату окончания"""
        return self.end_date.strftime('%d.%m.%Y') if self.end_date else '—'
    
    @property
    def duration_days(self):
        """Возвращает продолжительность обучения в днях"""
        if self.start_date and self.end_date:
            return (self.end_date - self.start_date).days + 1
        return None
    
    def clean(self):
        """Валидация модели"""
        from django.core.exceptions import ValidationError
        if self.start_date and self.end_date:
            if self.start_date > self.end_date:
                raise ValidationError(_('Дата начала не может быть позже даты окончания'))
        super().clean()


class Supplement(models.Model):
    """Модель для дополнительных соглашений к договорам"""
    
    class SupplementStatus(models.TextChoices):
        DRAFT = 'DRAFT', _('Черновик')
        NEGOTIATION = 'NEGOTIATION', _('На согласовании')
        SIGNING = 'SIGNING', _('На подписании')
        SIGNED = 'SIGNED', _('Подписан')
    
    agreement = models.ForeignKey(
        EduAgreement,
        verbose_name=_('Основной договор'),
        on_delete=models.CASCADE,
        related_name='supplements'
    )
    number = models.CharField(_('Номер допсоглашения'), max_length=100)
    signing_date = models.DateField(_('Дата подписания'), null=True, blank=True)
    description = models.TextField(_('Описание изменений'))
    status = models.CharField(
        _('Статус'),
        max_length=20,
        choices=SupplementStatus.choices,
        default=SupplementStatus.DRAFT
    )
    document_link = models.URLField(_('Ссылка на документ'), blank=True)
    created_at = models.DateTimeField(_('Дата создания'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Дата обновления'), auto_now=True)
    
    class Meta:
        verbose_name = _('Дополнительное соглашение')
        verbose_name_plural = _('Дополнительные соглашения')
        ordering = ['agreement', '-signing_date', '-created_at']
        unique_together = ['agreement', 'number']
    
    def __str__(self):
        return f"Допсоглашение №{self.number} к договору {self.agreement.number}"


class QuotaChange(models.Model):
    """Модель для отслеживания изменений квот в дополнительных соглашениях"""
    
    class ChangeType(models.TextChoices):
        ADD = 'ADD', _('Добавление')
        REMOVE = 'REMOVE', _('Удаление')
        MODIFY = 'MODIFY', _('Изменение')
    
    supplement = models.ForeignKey(
        Supplement,
        verbose_name=_('Дополнительное соглашение'),
        on_delete=models.CASCADE,
        related_name='quota_changes'
    )
    change_type = models.CharField(
        _('Тип изменения'),
        max_length=10,
        choices=ChangeType.choices
    )
    education_program = models.ForeignKey(
        EducationProgram,
        verbose_name=_('Программа обучения'),
        on_delete=models.PROTECT,
        related_name='quota_changes'
    )
    region = models.CharField(_('Регион'), max_length=255)
    old_quantity = models.PositiveIntegerField(
        _('Старое количество'),
        null=True,
        blank=True,
        help_text=_('Для изменений - предыдущее значение')
    )
    new_quantity = models.PositiveIntegerField(
        _('Новое количество'),
        help_text=_('Для добавления/изменения - новое значение')
    )
    comment = models.TextField(_('Комментарий'), blank=True)
    created_at = models.DateTimeField(_('Дата создания'), auto_now_add=True)
    
    class Meta:
        verbose_name = _('Изменение квоты')
        verbose_name_plural = _('Изменения квот')
        ordering = ['supplement', 'education_program', 'region']
    
    def __str__(self):
        action = {
            'ADD': 'Добавлено',
            'REMOVE': 'Удалено',
            'MODIFY': 'Изменено'
        }.get(self.change_type, '')
        return f"{action}: {self.education_program.name} - {self.region}"
    
    def clean(self):
        """Валидация изменений"""
        if self.change_type == self.ChangeType.MODIFY and self.old_quantity is None:
            raise ValidationError(_('Для изменения квоты необходимо указать старое количество'))
        
        if self.change_type == self.ChangeType.REMOVE:
            # Проверяем, существует ли такая квота
            actual_quotas = self.supplement.agreement.get_actual_quotas()
            quota_exists = any(
                q['program'].id == self.education_program_id and q['region'] == self.region
                for q in actual_quotas
            )
            if not quota_exists:
                raise ValidationError(_('Невозможно удалить несуществующую квоту'))
