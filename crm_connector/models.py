from django.db import models
from django.utils import timezone
import json
from django.db.models import JSONField
from simple_history.models import HistoricalRecords

# Добавляем константы для типов стадий
STAGE_TYPE_PROCESS = 'process'
STAGE_TYPE_SUCCESS = 'success'
STAGE_TYPE_FAILURE = 'failure'

REGION_CHOICES = [
    # Список регионов, лучше скрыть
    ('969', 'Амурская область'),
    ('971', 'Архангельская область'),
    ('973', 'Астраханская область'),
    ('975', 'Белгородская область'),
    ('977', 'Брянская область'),
    ('979', 'Владимирская область'),
    ('981', 'Волгоградская область'),
    ('983', 'Вологодская область'),
    ('985', 'Воронежская область'),
    ('987', 'Донецкая Народная Республика'),
    ('989', 'Еврейская автономная область'),
    ('991', 'Забайкальский край'),
    ('993', 'Запорожская область'),
    ('995', 'Ивановская область'),
    ('997', 'Иркутская область'),
    ('999', 'Кабардино-Балкарская Республика'),
    ('1001', 'Калининградская область'),
    ('1003', 'Калужская область'),
    ('1005', 'Камчатский край'),
    ('1007', 'Карачаево-Черкесская Республика'),
    ('1009', 'Кемеровская область'),
    ('1011', 'Кировская область'),
    ('1013', 'Костромская область'),
    ('1015', 'Краснодарский край'),
    ('1017', 'Красноярский край'),
    ('1019', 'Крым'),
    ('1021', 'Курганская область'),
    ('1023', 'Курская область'),
    ('1025', 'Ленинградская область'),
    ('1027', 'Липецкая область'),
    ('1029', 'Луганская Народная Республика'),
    ('1031', 'Магаданская область'),
    ('1033', 'город Москва'),
    ('1035', 'Московская область'),
    ('1037', 'Мурманская область'),
    ('1039', 'Ненецкий автономный округ'),
    ('1041', 'Нижегородская область'),
    ('1043', 'Новгородская область'),
    ('1045', 'Новосибирская область'),
    ('1047', 'Омская область'),
    ('1049', 'Оренбургская область'),
    ('1051', 'Орловская область'),
    ('1053', 'Пензенская область'),
    ('1055', 'Пермский край'),
    ('1057', 'Приморский край'),
    ('1059', 'Псковская область'),
    ('1061', 'Республика Адыгея'),
    ('1063', 'Республика Алтай'),
    ('1065', 'Республика Башкортостан'),
    ('1067', 'Республика Бурятия'),
    ('1069', 'Республика Дагестан'),
    ('1071', 'Республика Ингушетия'),
    ('1073', 'Республика Калмыкия'),
    ('1075', 'Республика Карелия'),
    ('1077', 'Республика Коми'),
    ('1079', 'Республика Марий Эл'),
    ('1081', 'Республика Мордовия'),
    ('1083', 'Республика Саха (Якутия)'),
    ('1085', 'Республика Северная Осетия — Алания'),
    ('1087', 'Республика Татарстан'),
    ('1089', 'Республика Тыва'),
    ('1091', 'Республика Хакасия'),
    ('1093', 'Ростовская область'),
    ('1095', 'Рязанская область'),
    ('1097', 'Самарская область'),
    ('1099', 'город Санкт-Петербург'),
    ('1101', 'Саратовская область'),
    ('1103', 'Сахалинская область'),
    ('1105', 'Свердловская область'),
    ('1107', 'Севастополь'),
    ('1109', 'Смоленская область'),
    ('1111', 'Ставропольский край'),
    ('1113', 'Тамбовская область'),
    ('1115', 'Тверская область'),
    ('1117', 'Томская область'),
    ('1119', 'Тульская область'),
    ('1121', 'Тюменская область'),
    ('1123', 'Удмуртская Республика'),
    ('1125', 'Ульяновская область'),
    ('1127', 'Хабаровский край'),
    ('1129', 'Ханты-Мансийский автономный округ — Югра'),
    ('1131', 'Херсонская область'),
    ('1133', 'Челябинская область'),
    ('1135', 'Чеченская Республика'),
    ('1137', 'Чувашская Республика - Чувашия'),
    ('1139', 'Чукотский автономный округ'),
    ('1141', 'Ямало-Ненецкий автономный округ'),
    ('1143', 'Ярославская область'),
]

EDUCATION_PROGRAMM = [
  ("329", "Основы искусственного интеллекта"),
  ("2661", "Инструменты искусственного интеллекта в педагогике"),
  ("327", "Специалист по эксплуатации беспилотных летательных аппаратов"),
  ("319", "Графический дизайнер"),
  ("331", "Бухгалтер"),
  ("317", "Специалист по информационным системам и программированию"),
  ("519", "Оператор беспилотных авиационных систем"),
  ("2311", "Оператор беспилотных авиационных систем (ЦОПП)"),
  ("321", "Специалист по эксплуатации токарного и фрезерного оборудования"),
  ("323", "Мастер слесарно-электромонтажных работ"),
  ("325", "Специалист по эксплуатации станков с программным управлением"),
  ("2293", "Специалист по борьбе с беспилотными летательными аппаратами и защите объектов (РЭБ)"),
  ("2299", "Специалист по информационным системам в области искусственного интеллекта"),
  ("2305", "Инструктор по обучению операторов (внешних пилотов) беспилотных воздушных судов с максимальной взлетной массой 30 кг и менее."),
  ("2319", "Повар"),
  ("2321", "Актуальные вопросы организации воспитательной деятельности в системе среднего профессионального образования"),
  ("2669", "БПЛА"),
  ("2671", "РЭБ 72"),
  ("2673", "Специалист по эксплуатации беспилотных авиационных систем в сфере лесного хозяйства"),
  ("2675", "ОБПЛА (Оператор беспилотных авиационных систем (с максимальной взлетной массой 30 килограммов и менее))"),
  ("2677", "РЭБ 144"),
  ("2679", "ИИ в культуре")
]


# Словарь с цветами для типов стадий
STAGE_TYPE_COLORS = {
    STAGE_TYPE_PROCESS: '#5bc0de',  # синий
    STAGE_TYPE_SUCCESS: '#5cb85c',  # зеленый
    STAGE_TYPE_FAILURE: '#d9534f',  # красный
}

STAGE_TYPE_CHOICES = [
    (STAGE_TYPE_PROCESS, 'В процессе'),
    (STAGE_TYPE_SUCCESS, 'Успешное завершение'),
    (STAGE_TYPE_FAILURE, 'Неуспешное завершение'),
]

class Pipeline(models.Model):
    """Модель для хранения воронок продаж из Битрикс24"""
    bitrix_id = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    sort = models.IntegerField(default=500)
    is_active = models.BooleanField(default=True)
    is_main = models.BooleanField(default=False)  # Флаг основной воронки
    last_updated = models.DateTimeField(auto_now=True)
    last_sync = models.DateTimeField(null=True)  # Время последней синхронизации
    
    # История изменений
    history = HistoricalRecords()
    
    def __str__(self):
        status = "активна" if self.is_active else "неактивна"
        main = " (основная)" if self.is_main else ""
        return f"{self.name}{main} ({status})"
    
    class Meta:
        verbose_name = "Воронка продаж"
        verbose_name_plural = "Воронки продаж"
        ordering = ['-is_main', 'sort']  # Сначала основная воронка, потом по сортировке

    def is_stale(self, max_age_hours=1):
        """Проверяет, устарели ли данные воронки"""
        if not self.last_sync:
            return True
        
        max_age = timezone.timedelta(hours=max_age_hours)
        return timezone.now() - self.last_sync > max_age

    @staticmethod
    def get_main_pipeline():
        """Возвращает основную воронку продаж"""
        main = Pipeline.objects.filter(is_main=True).first()
        if not main:
            # Если основная не найдена, пробуем найти воронку с ID=0
            main = Pipeline.objects.filter(bitrix_id='0').first()
        return main

class Stage(models.Model):
    """Модель для хранения этапов воронок продаж из Битрикс24"""
    bitrix_id = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=255)
    sort = models.IntegerField(default=500)
    color = models.CharField(max_length=50, blank=True, null=True)
    pipeline = models.ForeignKey(Pipeline, on_delete=models.CASCADE, related_name='stages')
    status_id = models.CharField(max_length=50, blank=True, null=True)
    success_probability = models.IntegerField(default=0)  # Вероятность успеха в процентах
    type = models.CharField(max_length=20, choices=STAGE_TYPE_CHOICES, default=STAGE_TYPE_PROCESS)
    
    # История изменений
    history = HistoricalRecords()
    
    # Автоматически устанавливаем цвет на основе типа стадии
    def save(self, *args, **kwargs):
        # Назначаем цвет в зависимости от типа, но не меняем тип
        self.set_color_by_type()
        super().save(*args, **kwargs)
    
    def set_color_by_type(self):
        """Устанавливает цвет в зависимости от типа стадии"""
        self.color = STAGE_TYPE_COLORS.get(self.type, STAGE_TYPE_COLORS[STAGE_TYPE_PROCESS])
    
    def __str__(self):
        return f"{self.name} ({self.pipeline.name})"
    
    class Meta:
        verbose_name = "Этап воронки"
        verbose_name_plural = "Этапы воронок"
        ordering = ['pipeline__sort', 'sort']

class Lead(models.Model):
    """Модель для хранения лидов из Битрикс24"""
    bitrix_id = models.IntegerField(unique=True)
    title = models.CharField(max_length=255)
    name = models.CharField(max_length=255, blank=True, null=True)
    phone = models.CharField(max_length=50, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    status = models.CharField(max_length=100)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Лид'
        verbose_name_plural = 'Лиды'
        
    def __str__(self):
        return f"{self.title} ({self.bitrix_id})"

class Company(models.Model):
    """Модель для хранения компаний из Битрикс24"""
    bitrix_id = models.IntegerField(unique=True)
    title = models.CharField(max_length=255)
    head = models.CharField(max_length=10, blank=True, null=True)
    child = models.CharField(max_length=10, blank=True, null=True)

    class Meta:
        verbose_name = 'Компанию'
        verbose_name_plural = 'Компании'

    def __str__(self):
        return f"{self.title}"

class Deal(models.Model):
    """Модель для хранения сделок из Битрикс24"""
    bitrix_id = models.IntegerField(unique=True)
    title = models.CharField(max_length=255)
    pipeline = models.ForeignKey(Pipeline, on_delete=models.SET_NULL, null=True, related_name='deals')
    stage = models.ForeignKey(Stage, on_delete=models.SET_NULL, null=True, related_name='deals')
    company = models.ForeignKey(Company, on_delete=models.SET_NULL, null=True, related_name='deals')
    program = models.CharField(max_length=255, choices=EDUCATION_PROGRAMM, null=True, blank=True)
    region = models.CharField(max_length=10, choices=REGION_CHOICES, blank=True,null=True)
    amount = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)
    created_at = models.DateTimeField()
    closed_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    responsible_id = models.IntegerField(null=True, blank=True)
    category_id = models.IntegerField(default=0)  # ID воронки
    is_closed = models.BooleanField(default=False)
    is_new = models.BooleanField(default=True)
    probability = models.IntegerField(default=0)  # Вероятность успеха в процентах
    last_sync = models.DateTimeField(null=True, blank=True)
    
    # Детальные данные в формате JSON
    details = JSONField(null=True, blank=True)
    
    # История изменений
    history = HistoricalRecords()
    
    class Meta:
        verbose_name = 'Сделка'
        verbose_name_plural = 'Сделки'
        indexes = [
            models.Index(fields=['pipeline', 'stage']),
            models.Index(fields=['created_at']),
            models.Index(fields=['is_closed'])
        ]
        
    def __str__(self):
        return f"{self.title} ({self.bitrix_id})"
    
    def get_detail(self, field_name, default=None):
        """Получает значение поля из деталей сделки"""
        if not self.details:
            return default
        return self.details.get(field_name, default)
    
    @property
    def pipeline_name(self):
        """Возвращает название воронки"""
        return self.pipeline.name if self.pipeline else "Нет воронки"
    
    @property
    def stage_name(self):
        """Возвращает название этапа"""
        return self.stage.name if self.stage else "Нет этапа"
    
    @property 
    def responsible_name(self):
        """Возвращает имя ответственного"""
        if not self.details or 'ASSIGNED_BY_NAME' not in self.details:
            return "Неизвестно"
        return f"{self.details.get('ASSIGNED_BY_NAME', '')} {self.details.get('ASSIGNED_BY_LAST_NAME', '')}"
    
    @property
    def days_in_pipeline(self):
        """Возвращает количество дней в воронке"""
        if not self.created_at:
            return 0
        end_date = self.closed_at if self.is_closed and self.closed_at else timezone.now()
        return (end_date - self.created_at).days

    def save(self, *args, **kwargs):
        if not self.last_sync:
            self.last_sync = timezone.now()
        super().save(*args, **kwargs)

class Contact(models.Model):
    """Модель для хранения контактов из Битрикс24"""
    bitrix_id = models.IntegerField(unique=True)
    name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255, blank=True, null=True)
    phone = models.CharField(max_length=50, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Контакт'
        verbose_name_plural = 'Контакты'
        
    def __str__(self):
        return f"{self.name} {self.last_name or ''} ({self.bitrix_id})"

class AtlasProgram(models.Model):
    """Модель для хранения программ из системы Атлас"""
    program_id = models.CharField(max_length=255, unique=True, verbose_name="ID Программы")
    title = models.CharField(max_length=255, verbose_name="Название программы")
    short_title = models.CharField(max_length=255, verbose_name="Короткое название программы", blank=True, null=True)
    section = JSONField(max_length=255, verbose_name="Разделы", blank=True, null=True)
    topics = JSONField(max_length=255, verbose_name="Темы", blank=True, null=True)
    class Meta:
        verbose_name = 'Программу Атлас'
        verbose_name_plural = 'Программы Атлас'

class AtlasApplication(models.Model):
    """Модель для хранения заявок из системы Атлас"""
    # Основные поля из выгрузки
    application_id = models.CharField(max_length=255, unique=True, verbose_name="ID заявки в Атласе")
    full_name = models.CharField(max_length=500, verbose_name="ФИО")
    phone = models.CharField(max_length=50, blank=True, null=True, verbose_name="Телефон")
    email = models.EmailField(blank=True, null=True, verbose_name="Email")
    region = models.CharField(max_length=255, blank=True, null=True, verbose_name="Регион")
    address  = models.CharField(max_length=255, null=True, blank=True, verbose_name="Адрес")
    postal_code = models.CharField(max_length=255, null=True, blank=True, verbose_name="Почтовый индекс")
    program = models.CharField(max_length=255, null=True, blank=True, verbose_name="Программа обучения")
    last_active = models.DateTimeField(null=True, blank=True, verbose_name="Последняя активность")
    potok = models.CharField(max_length=255, blank=True, null=True, verbose_name="Поток")
    education_progress = models.CharField(max_length=255, null=True, blank=True, verbose_name="Прогресс")
    JSON_ed_progress = models.JSONField(max_length=1024, null=True, blank=True, verbose_name="Прогресс JSON")
    
    # Связь со сделкой в Bitrix24
    deal = models.ForeignKey(Deal, on_delete=models.SET_NULL, null=True, blank=True, 
                           related_name='atlas_applications', verbose_name="Связанная сделка")
    
    # Дополнительные поля
    raw_data = JSONField(default=dict, verbose_name="Исходные данные из выгрузки")
    
    # Поля адреса из формы
    form_postal_code = models.CharField(max_length=10, blank=True, null=True, verbose_name="Почтовый индекс (из формы)")
    form_region = models.CharField(max_length=255, blank=True, null=True, verbose_name="Регион (из формы)")
    form_settlement = models.CharField(max_length=255, blank=True, null=True, verbose_name="Населенный пункт")
    form_street = models.CharField(max_length=255, blank=True, null=True, verbose_name="Улица/другое")
    form_house = models.CharField(max_length=50, blank=True, null=True, verbose_name="Дом/другое")
    form_building = models.CharField(max_length=50, blank=True, null=True, verbose_name="Корпус/другое")
    form_apartment = models.CharField(max_length=50, blank=True, null=True, verbose_name="Квартира/другое")
    
    # Файлы заявлений
    generated_application = models.FileField(upload_to='applications/generated/', blank=True, null=True, verbose_name="Сгенерированное заявление")
    signed_application = models.FileField(upload_to='applications/signed/', blank=True, null=True, verbose_name="Подписанное заявление")
    
    # Статусы синхронизации
    is_synced = models.BooleanField(default=False, verbose_name="Синхронизировано с Bitrix24")
    sync_errors = models.TextField(blank=True, null=True, verbose_name="Ошибки синхронизации")
    
    # Временные метки
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_sync = models.DateTimeField(null=True, blank=True)
    
    # История изменений
    history = HistoricalRecords()
    
    class Meta:
        verbose_name = "Заявка из Атласа"
        verbose_name_plural = "Заявки из Атласа"
        indexes = [
            models.Index(fields=['phone']),
            models.Index(fields=['email']),
            models.Index(fields=['full_name', 'region']),
        ]
    
    def __str__(self):
        return f"Заявка {self.application_id}: {self.full_name}"
    
    def normalize_phone(self):
        """Нормализует номер телефона"""
        if not self.phone:
            return None
        # Удаляем все символы кроме цифр
        phone = ''.join(filter(str.isdigit, self.phone))
        # Приводим к единому формату
        if len(phone) == 11 and phone.startswith('8'):
            phone = '7' + phone[1:]
        elif len(phone) == 10:
            phone = '7' + phone
        return phone
    
    def normalize_email(self):
        """Нормализует email"""
        if not self.email:
            return None
        return self.email.lower().strip()
    
    def normalize_full_name(self):
        """Нормализует ФИО"""
        if not self.full_name:
            return None
        # Убираем лишние пробелы и приводим к единому регистру
        return ' '.join(self.full_name.strip().split()).title()


class AtlasStatus(models.Model):
    """Модель для хранения статусов заявок в системе Атлас"""
    name = models.CharField(max_length=255, unique=True, verbose_name="Название статуса")
    order = models.IntegerField(default=0, verbose_name="Порядковый номер")
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    
    class Meta:
        verbose_name = "Статус Атлас"
        verbose_name_plural = "Статусы Атлас"
        ordering = ['order', 'name']
    
    def __str__(self):
        return f"{self.name} (порядок: {self.order})"


class RRStatus(models.Model):
    """Модель для хранения статусов заявок в РР (Работа России)"""
    name = models.CharField(max_length=255, unique=True, verbose_name="Название статуса")
    order = models.IntegerField(default=0, verbose_name="Порядковый номер")
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    
    class Meta:
        verbose_name = "Статус РР"
        verbose_name_plural = "Статусы РР"
        ordering = ['order', 'name']
    
    def __str__(self):
        return f"{self.name} (порядок: {self.order})"


class StageRule(models.Model):
    """Модель для правил определения этапа воронки на основе статусов"""
    # Связь с воронкой
    pipeline = models.ForeignKey(Pipeline, on_delete=models.CASCADE, related_name='stage_rules', 
                               verbose_name="Воронка")
    
    # Целевая стадия, которая будет установлена при совпадении правила
    target_stage = models.ForeignKey(Stage, on_delete=models.CASCADE, related_name='stage_rules',
                                   verbose_name="Целевая стадия")
    
    # Условия для статусов (может быть указан один или оба)
    atlas_status = models.ForeignKey(AtlasStatus, on_delete=models.CASCADE, null=True, blank=True,
                                   verbose_name="Статус в Атлас")
    rr_status = models.ForeignKey(RRStatus, on_delete=models.CASCADE, null=True, blank=True,
                                verbose_name="Статус в РР")
    
    # Приоритет правила (меньше = выше приоритет)
    priority = models.IntegerField(default=100, verbose_name="Приоритет")
    
    # Активность правила
    is_active = models.BooleanField(default=True, verbose_name="Активно")
    
    # Описание правила для удобства
    description = models.TextField(blank=True, verbose_name="Описание правила")
    
    class Meta:
        verbose_name = "Правило определения стадии"
        verbose_name_plural = "Правила определения стадий"
        ordering = ['priority', 'id']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(atlas_status__isnull=False) | models.Q(rr_status__isnull=False),
                name='at_least_one_status_required'
            )
        ]
    
    def __str__(self):
        conditions = []
        if self.atlas_status:
            conditions.append(f"Атлас: {self.atlas_status.name}")
        if self.rr_status:
            conditions.append(f"РР: {self.rr_status.name}")
        return f"{' И '.join(conditions)} → {self.target_stage.name} (приоритет: {self.priority})"
    
    def matches(self, atlas_status_name=None, rr_status_name=None):
        """Проверяет, соответствует ли правило заданным статусам"""
        if not self.is_active:
            return False
        
        # Если в правиле указан статус Атлас, проверяем его
        if self.atlas_status:
            if atlas_status_name != self.atlas_status.name:
                return False
        
        # Если в правиле указан статус РР, проверяем его
        if self.rr_status:
            if rr_status_name != self.rr_status.name:
                return False
        
        return True
    
    @classmethod
    def determine_stage_for_deal(cls, pipeline, atlas_status_name=None, rr_status_name=None):
        """Определяет стадию для сделки на основе статусов"""
        # Получаем активные правила для воронки, отсортированные по приоритету (от большего к меньшему)
        rules = cls.objects.filter(
            pipeline=pipeline,
            is_active=True
        ).select_related('target_stage', 'atlas_status', 'rr_status').order_by('-priority', 'id')
        
        # Проверяем правила по порядку
        for rule in rules:
            if rule.matches(atlas_status_name, rr_status_name):
                return rule.target_stage
        
        # Если ни одно правило не подошло, возвращаем None
        return None 