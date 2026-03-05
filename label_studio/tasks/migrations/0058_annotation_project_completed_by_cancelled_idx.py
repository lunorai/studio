from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('tasks', '0057_annotation_proj_result_octlen_idx_async'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='annotation',
            index=models.Index(
                fields=['project', 'completed_by', 'was_cancelled'],
                name='tsk_ann_prj_usr_can_idx',
            ),
        ),
    ]
