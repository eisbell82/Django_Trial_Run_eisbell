from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("repository", "0013_add_image_to_dataset_and_sample"),
    ]

    operations = [
        migrations.AddField(
            model_name="samplecolumn",
            name="group",
            field=models.CharField(
                choices=[("characteristics", "Sample characteristics"), ("data", "Sample data")],
                default="data",
                max_length=20,
            ),
        ),
    ]
