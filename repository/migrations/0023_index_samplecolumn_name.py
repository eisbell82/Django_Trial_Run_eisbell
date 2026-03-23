from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('repository', '0022_sample_notes'),
    ]

    operations = [
        migrations.AlterField(
            model_name='samplecolumn',
            name='name',
            field=models.CharField(db_index=True, max_length=200),
        ),
    ]
