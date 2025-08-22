"""This file and its contents are licensed under the Apache License 2.0. Please see the included NOTICE for copyright information and LICENSE for a copy of the license.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0012_user_lunor_username'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='lunor_userId',
            field=models.CharField(blank=True, max_length=256, null=True, verbose_name='lunor user id'),
        ),
        migrations.RemoveField(
            model_name='user',
            name='lunor_username',
        ),
    ]


