from typing import Optional

from django.db import transaction

from projects.models import Project
from projects.models_user_assignment import UserTaskAssignment
from tasks.models import Task
from users.models import User


def get_or_create_user_assignment(user: User, project: Project) -> Optional[UserTaskAssignment]:
    """
    Ensure the given user has a fixed circular batch of tasks for this project.

    Behaviour:
    - If Project.per_user_batch_size is empty or 0 -> return None, meaning
      the project should use the default task presentation logic.
    - If the requesting user is the project owner or a superuser -> return None
      so owners/org admins always see all tasks.
    - Otherwise, use Project.global_task_index as the global pointer and
      Project.per_user_batch_size as batch size (10-20 typical), wrapping
      around when reaching the end of the task list.
    """
    # Project owners and superusers should see the full task set
    if getattr(user, 'is_superuser', False) or user == getattr(project, 'created_by', None):
        return None

    batch_size = project.per_user_batch_size or 0
    if batch_size <= 0:
        # No special batch behaviour configured for this project
        return None

    total = Task.objects.filter(project=project).count()
    expected_count = min(batch_size, total) if total > 0 else 0

    assignment, created = UserTaskAssignment.objects.get_or_create(user=user, project=project)
    if not created and assignment.tasks.count() == expected_count:
        return assignment

    with transaction.atomic():
        # Re-check inside transaction to avoid race conditions
        assignment, created = UserTaskAssignment.objects.select_for_update().get_or_create(
            user=user,
            project=project,
        )
        if not created and assignment.tasks.count() == expected_count:
            return assignment

        tasks_qs = Task.objects.filter(project=project).order_by('id').values_list('id', flat=True)
        if total == 0:
            assignment.tasks.clear()
            return assignment

        start = project.global_task_index % total
        # Fetch only the required task-id window(s) instead of loading all task ids.
        selected_ids = []
        remaining = batch_size
        cursor = start
        while remaining > 0:
            chunk_size = min(remaining, total - cursor)
            selected_ids.extend(list(tasks_qs[cursor : cursor + chunk_size]))
            remaining -= chunk_size
            cursor = 0

        assignment.tasks.set(Task.objects.filter(id__in=selected_ids))

        project.global_task_index = (project.global_task_index + batch_size) % total
        project.save(update_fields=['global_task_index'])

    return assignment
