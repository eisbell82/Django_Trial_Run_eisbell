from django.db import migrations, models


def move_column_sections(apps, schema_editor):
    DocsSection = apps.get_model('repository', 'DocsSection')
    DocsSection.objects.filter(
        tab='naming',
        heading__in=['Column Names', 'Column Groups'],
    ).update(tab='columns')


def reverse_move(apps, schema_editor):
    DocsSection = apps.get_model('repository', 'DocsSection')
    DocsSection.objects.filter(
        tab='columns',
        heading__in=['Column Names', 'Column Groups'],
    ).update(tab='naming')


class Migration(migrations.Migration):

    dependencies = [
        ('repository', '0019_add_docssection'),
    ]

    operations = [
        migrations.AlterField(
            model_name='docssection',
            name='tab',
            field=models.CharField(
                choices=[
                    ('overview', 'Overview'),
                    ('naming', 'Data Structure'),
                    ('columns', 'Column Structure'),
                ],
                default='overview',
                max_length=20,
            ),
        ),
        migrations.RunPython(move_column_sections, reverse_move),
    ]
