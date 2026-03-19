from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("repository", "0020_add_columns_tab"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="dataset",
            name="version",
        ),
    ]
