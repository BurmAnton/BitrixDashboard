from django.db import models
from django.utils.translation import gettext_lazy as _

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
