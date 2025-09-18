from django.db import migrations, models
import django.conf
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0033_project_challenge_status'),
        migrations.swappable_dependency(django.conf.settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='FinalSubmission',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('submitted_user_id', models.IntegerField(help_text='Django user id at time of submission')),
                ('lunor_user_id', models.CharField(blank=True, default='', max_length=255, null=True)),
                ('challenge_id', models.IntegerField(blank=True, default=None, null=True)),
                ('round', models.IntegerField(blank=True, default=None, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='created at')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='final_submissions', to='projects.project')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='final_submissions', to=django.conf.settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'final_submission',
            },
        ),
        migrations.AddConstraint(
            model_name='finalsubmission',
            constraint=models.UniqueConstraint(fields=('project', 'user', 'challenge_id', 'round'), name='unique_final_submission_per_user_project_round'),
        ),
    ]


