from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("repository", "0021_remove_dataset_version"),
    ]

    operations = [
        migrations.AddField(
            model_name="sample",
            name="notes",
            field=models.TextField(blank=True),
        ),
    ]
