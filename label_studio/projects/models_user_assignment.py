from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class UserTaskAssignment(models.Model):
    """
    Stores a fixed circular batch of tasks assigned to a particular user in a project.
    These assignments are used to ensure each user sees their own 10–20 questions
    and that they continue to see them even after annotating.
    """

    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.CASCADE,
        related_name='user_assignments',
        verbose_name=_('project'),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='task_assignments',
        verbose_name=_('user'),
    )
    tasks = models.ManyToManyField(
        'tasks.Task',
        related_name='user_assignments',
        verbose_name=_('tasks'),
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('project', 'user')
        verbose_name = _('user task assignment')
        verbose_name_plural = _('user task assignments')

    def __str__(self):
        return f'UserTaskAssignment(project={self.project_id}, user={self.user_id})'


