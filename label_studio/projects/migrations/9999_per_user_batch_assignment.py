from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0035_merge_0034_0031'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='global_task_index',
            field=models.PositiveIntegerField(
                default=0,
                verbose_name='global task index',
                help_text='Global pointer for circular per-user batch assignment.',
            ),
        ),
        migrations.AddField(
            model_name='project',
            name='per_user_batch_size',
            field=models.PositiveIntegerField(
                default=10,
                verbose_name='per user batch size',
                help_text='Number of tasks initially assigned to each user.',
            ),
        ),
    ]


