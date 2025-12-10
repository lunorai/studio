from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '9999_per_user_batch_assignment'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserTaskAssignment',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                (
                    'created_at',
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    'project',
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name='user_assignments',
                        to='projects.project',
                        verbose_name='project',
                    ),
                ),
                (
                    'tasks',
                    models.ManyToManyField(
                        blank=True,
                        related_name='user_assignments',
                        to='tasks.Task',
                        verbose_name='tasks',
                    ),
                ),
                (
                    'user',
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name='task_assignments',
                        to=settings.AUTH_USER_MODEL,
                        verbose_name='user',
                    ),
                ),
            ],
            options={
                'verbose_name': 'user task assignment',
                'verbose_name_plural': 'user task assignments',
                'unique_together': {('project', 'user')},
            },
        ),
    ]


