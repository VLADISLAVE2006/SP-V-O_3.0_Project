from django.db import migrations


def seed_roles(apps, schema_editor):
    role = apps.get_model("core", "Role")
    for name in ["user", "moderator", "admin"]:
        role.objects.get_or_create(name=name)


class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial")]
    operations = [migrations.RunPython(seed_roles, migrations.RunPython.noop)]
