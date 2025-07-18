# Generated by Django 4.2.19 on 2025-06-23 11:47

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import simple_history.models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('crm_connector', '0008_atlas_application'),
    ]

    operations = [
        migrations.CreateModel(
            name='HistoricalStage',
            fields=[
                ('id', models.BigIntegerField(auto_created=True, blank=True, db_index=True, verbose_name='ID')),
                ('bitrix_id', models.CharField(db_index=True, max_length=100)),
                ('name', models.CharField(max_length=255)),
                ('sort', models.IntegerField(default=500)),
                ('color', models.CharField(blank=True, max_length=50, null=True)),
                ('status_id', models.CharField(blank=True, max_length=50, null=True)),
                ('success_probability', models.IntegerField(default=0)),
                ('type', models.CharField(choices=[('process', 'В процессе'), ('success', 'Успешное завершение'), ('failure', 'Неуспешное завершение')], default='process', max_length=20)),
                ('history_id', models.AutoField(primary_key=True, serialize=False)),
                ('history_date', models.DateTimeField(db_index=True)),
                ('history_change_reason', models.CharField(max_length=100, null=True)),
                ('history_type', models.CharField(choices=[('+', 'Created'), ('~', 'Changed'), ('-', 'Deleted')], max_length=1)),
                ('history_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('pipeline', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='crm_connector.pipeline')),
            ],
            options={
                'verbose_name': 'historical Этап воронки',
                'verbose_name_plural': 'historical Этапы воронок',
                'ordering': ('-history_date', '-history_id'),
                'get_latest_by': ('history_date', 'history_id'),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name='HistoricalPipeline',
            fields=[
                ('id', models.BigIntegerField(auto_created=True, blank=True, db_index=True, verbose_name='ID')),
                ('bitrix_id', models.CharField(db_index=True, max_length=50)),
                ('name', models.CharField(max_length=255)),
                ('sort', models.IntegerField(default=500)),
                ('is_active', models.BooleanField(default=True)),
                ('is_main', models.BooleanField(default=False)),
                ('last_updated', models.DateTimeField(blank=True, editable=False)),
                ('last_sync', models.DateTimeField(null=True)),
                ('history_id', models.AutoField(primary_key=True, serialize=False)),
                ('history_date', models.DateTimeField(db_index=True)),
                ('history_change_reason', models.CharField(max_length=100, null=True)),
                ('history_type', models.CharField(choices=[('+', 'Created'), ('~', 'Changed'), ('-', 'Deleted')], max_length=1)),
                ('history_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'historical Воронка продаж',
                'verbose_name_plural': 'historical Воронки продаж',
                'ordering': ('-history_date', '-history_id'),
                'get_latest_by': ('history_date', 'history_id'),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name='HistoricalDeal',
            fields=[
                ('id', models.BigIntegerField(auto_created=True, blank=True, db_index=True, verbose_name='ID')),
                ('bitrix_id', models.IntegerField(db_index=True)),
                ('title', models.CharField(max_length=255)),
                ('amount', models.DecimalField(blank=True, decimal_places=2, max_digits=15, null=True)),
                ('created_at', models.DateTimeField()),
                ('closed_at', models.DateTimeField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(blank=True, editable=False)),
                ('responsible_id', models.IntegerField(blank=True, null=True)),
                ('category_id', models.IntegerField(default=0)),
                ('is_closed', models.BooleanField(default=False)),
                ('is_new', models.BooleanField(default=True)),
                ('probability', models.IntegerField(default=0)),
                ('last_sync', models.DateTimeField(blank=True, null=True)),
                ('details', models.JSONField(blank=True, null=True)),
                ('history_id', models.AutoField(primary_key=True, serialize=False)),
                ('history_date', models.DateTimeField(db_index=True)),
                ('history_change_reason', models.CharField(max_length=100, null=True)),
                ('history_type', models.CharField(choices=[('+', 'Created'), ('~', 'Changed'), ('-', 'Deleted')], max_length=1)),
                ('history_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('pipeline', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='crm_connector.pipeline')),
                ('stage', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='crm_connector.stage')),
            ],
            options={
                'verbose_name': 'historical Сделка',
                'verbose_name_plural': 'historical Сделки',
                'ordering': ('-history_date', '-history_id'),
                'get_latest_by': ('history_date', 'history_id'),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name='HistoricalAtlasApplication',
            fields=[
                ('id', models.BigIntegerField(auto_created=True, blank=True, db_index=True, verbose_name='ID')),
                ('application_id', models.CharField(db_index=True, max_length=255, verbose_name='ID заявки в Атласе')),
                ('full_name', models.CharField(max_length=500, verbose_name='ФИО')),
                ('phone', models.CharField(blank=True, max_length=50, null=True, verbose_name='Телефон')),
                ('email', models.EmailField(blank=True, max_length=254, null=True, verbose_name='Email')),
                ('region', models.CharField(blank=True, max_length=255, null=True, verbose_name='Регион')),
                ('raw_data', models.JSONField(default=dict, verbose_name='Исходные данные из выгрузки')),
                ('is_synced', models.BooleanField(default=False, verbose_name='Синхронизировано с Bitrix24')),
                ('sync_errors', models.TextField(blank=True, null=True, verbose_name='Ошибки синхронизации')),
                ('created_at', models.DateTimeField(blank=True, editable=False)),
                ('updated_at', models.DateTimeField(blank=True, editable=False)),
                ('last_sync', models.DateTimeField(blank=True, null=True)),
                ('history_id', models.AutoField(primary_key=True, serialize=False)),
                ('history_date', models.DateTimeField(db_index=True)),
                ('history_change_reason', models.CharField(max_length=100, null=True)),
                ('history_type', models.CharField(choices=[('+', 'Created'), ('~', 'Changed'), ('-', 'Deleted')], max_length=1)),
                ('deal', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='crm_connector.deal', verbose_name='Связанная сделка')),
                ('history_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'historical Заявка из Атласа',
                'verbose_name_plural': 'historical Заявки из Атласа',
                'ordering': ('-history_date', '-history_id'),
                'get_latest_by': ('history_date', 'history_id'),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
    ]
