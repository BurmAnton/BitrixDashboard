# Generated manually for main_date_quantity field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('education_planner', '0012_alternativequota'),
    ]

    operations = [
        migrations.AddField(
            model_name='quotadistribution',
            name='main_date_quantity',
            field=models.PositiveIntegerField(default=0, verbose_name='Количество для основной даты'),
        ),
        migrations.AlterField(
            model_name='quotadistribution',
            name='allocated_quantity',
            field=models.PositiveIntegerField(verbose_name='Общее выделенное количество'),
        ),
    ]
