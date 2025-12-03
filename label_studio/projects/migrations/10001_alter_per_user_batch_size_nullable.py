from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '10000_user_task_assignment'),
    ]

    operations = [
        migrations.AlterField(
            model_name='project',
            name='per_user_batch_size',
            field=models.PositiveIntegerField(
                null=True,
                blank=True,
                default=None,
                verbose_name='per user batch size',
                help_text=(
                    'Number of tasks initially assigned to each user for circular batching. '
                    'If empty or 0, tasks are shown using the default project behavior.'
                ),
            ),
        ),
    ]


