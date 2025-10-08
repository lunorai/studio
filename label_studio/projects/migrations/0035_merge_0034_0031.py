# Generated manually to merge two migration heads
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0034_final_submission"),
        ("projects", "0031_alter_project_show_ground_truth_first"),
    ]

    operations = [
        # This is an empty merge migration: it tells Django both branches are reconciled.
    ]
