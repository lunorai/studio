"""This file and its contents are licensed under the Apache License 2.0. Please see the included NOTICE for copyright information and LICENSE for a copy of the license.
"""
from core.version import get_short_version
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, render

from projects.models import Project


@login_required
def task_page(request, pk):
    # Enforce access rules:
    # - Organization owners (org.created_by == user) can access any project in their org
    # - Non-owners can only access projects they participate in
    project = get_object_or_404(Project, pk=pk)

    user = request.user
    active_org = getattr(user, 'active_organization', None)

    # Deny access if project doesn't belong to the user's active organization
    if not active_org or project.organization_id != getattr(active_org, 'id', None):
        raise Http404()

    is_owner = bool(active_org and getattr(active_org, 'created_by_id', None) == getattr(user, 'id', None))

    if not is_owner:
        lunor_user_id = getattr(user, 'lunor_userId', None)
        participants = project.participants or []
        if not lunor_user_id or lunor_user_id not in participants:
            raise Http404()

    response = {'version': get_short_version()}
    return render(request, 'base.html', response)
