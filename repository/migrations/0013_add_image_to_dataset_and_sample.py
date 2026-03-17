from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("repository", "0012_merge_dashboard_into_notebook"),
    ]

    operations = [
        migrations.AddField(
            model_name="dataset",
            name="image",
            field=models.ImageField(blank=True, null=True, upload_to="datasets/images/"),
        ),
        migrations.AddField(
            model_name="sample",
            name="image",
            field=models.ImageField(blank=True, null=True, upload_to="samples/photos/"),
        ),
    ]
