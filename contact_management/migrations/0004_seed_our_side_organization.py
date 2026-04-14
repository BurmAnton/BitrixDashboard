from django.db import migrations


def seed_our_side_organization(apps, schema_editor):
    Organization = apps.get_model("contact_management", "Organization")
    defaults = {
        "name": "Союз энегргетиков Поволжья",
        "full_name": "Союз энегргетиков Поволжья",
        "is_our_side": True,
    }
    organization, created = Organization.objects.get_or_create(
        inn="6321261206",
        defaults=defaults,
    )
    if not created and not organization.is_our_side:
        organization.is_our_side = True
        organization.save(update_fields=["is_our_side"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("contact_management", "0003_historicalorganization_is_our_side_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_our_side_organization, noop_reverse),
    ]
