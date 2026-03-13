from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("repository", "0005_remove_specimen_fields_add_experiment_date"),
    ]

    operations = [
        migrations.AddField(
            model_name="samplecolumn",
            name="unit",
            field=models.CharField(blank=True, default="", max_length=50),
        ),
    ]
