import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("repository", "0014_samplecolumn_group"),
    ]

    operations = [
        migrations.CreateModel(
            name="SamplePhoto",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ("image", models.ImageField(upload_to="samples/photos/")),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                (
                    "sample",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="photos",
                        to="repository.sample",
                    ),
                ),
            ],
            options={"ordering": ["uploaded_at"]},
        ),
        migrations.RemoveField(
            model_name="sample",
            name="image",
        ),
    ]
