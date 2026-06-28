import json

import pytest
from django.db import connection
from django.db.models.query import QuerySet
from django.test.utils import CaptureQueriesContext
from projects.api import (
    FinalSubmissionCheckAPI,
    _serialize_final_submission_tasks,
    _set_final_submission_upload_status,
)
from rest_framework.test import APIRequestFactory, force_authenticate
from tasks.models import AnnotationDraft
from tests.utils import make_annotation, make_prediction, make_project, make_task
from users.models import User


@pytest.mark.django_db
def test_update_tasks_counters_and_task_states(business_client):
    project = make_project({}, business_client.user, use_ml_backend=False)

    # CHECK EMPTY LIST
    ids = []
    obj = project._update_tasks_counters_and_task_states(ids, True, True, True)
    assert obj == 0

    tasks = [{'data': {'location': 'London', 'text': 'text A'}}, {'data': {'location': 'London', 'text': 'text B'}}]
    # upload tasks with annotations
    r = business_client.post(
        f'/api/projects/{project.id}/tasks/bulk', data=json.dumps(tasks), content_type='application/json'
    )
    assert r.status_code == 201

    # CHECK LIST with IDS
    ids = list(project.tasks.all().values_list('id', flat=True))
    obj = project._update_tasks_counters_and_task_states(ids, True, True, True)
    assert obj == 0

    # CHECK SET with IDS
    ids = set(project.tasks.all().values_list('id', flat=True))
    obj = project._update_tasks_counters_and_task_states(ids, True, True, True)
    assert obj == 0


@pytest.mark.django_db
def test_project_all_members(business_client):
    project = make_project({}, business_client.user, use_ml_backend=False)
    members = project.all_members

    assert isinstance(members, QuerySet)
    assert isinstance(members.first(), User)


@pytest.mark.django_db
def test_final_submission_check_uses_cache(business_client):
    project = make_project({}, business_client.user, use_ml_backend=False)
    factory = APIRequestFactory()
    view = FinalSubmissionCheckAPI.as_view()
    path = f'/api/projects/{project.id}/final-submission/check/'

    request = factory.get(path)
    force_authenticate(request, user=business_client.user)
    first_response = view(request, pk=project.id)

    assert first_response.status_code == 200
    assert first_response.data == {'exists': False, 'id': None}

    cached_request = factory.get(path)
    force_authenticate(cached_request, user=business_client.user)
    with CaptureQueriesContext(connection) as queries:
        cached_response = view(cached_request, pk=project.id)

    assert cached_response.status_code == 200
    assert cached_response.data == {'exists': False, 'id': None}
    assert len(queries) == 0, queries.captured_queries


@pytest.mark.django_db
def test_final_submission_check_updates_after_create(business_client):
    project = make_project({}, business_client.user, use_ml_backend=False)
    check_url = f'/api/projects/{project.id}/final-submission/check/'
    create_url = f'/api/projects/{project.id}/final-submission/'

    first_check = business_client.get(check_url)
    assert first_check.status_code == 200
    assert first_check.json() == {'exists': False, 'id': None}

    create_response = business_client.post(create_url)
    assert create_response.status_code == 201

    second_check = business_client.get(check_url)
    assert second_check.status_code == 200
    assert second_check.json()['exists'] is True
    assert second_check.json()['id'] == create_response.json()['id']


@pytest.mark.django_db
def test_final_submission_export_tasks_are_filtered_and_lightweight(business_client, annotator_client):
    project = make_project({}, business_client.user, use_ml_backend=False)
    task = make_task({'data': {'text': 'final submission task'}}, project)

    own_annotation = make_annotation({'result': [], 'completed_by': business_client.user}, task.id)
    make_annotation({'result': [], 'completed_by': annotator_client.user}, task.id)
    prediction = make_prediction({'result': []}, task.id)
    draft = AnnotationDraft.objects.create(task=task, user=business_client.user, result=[])

    tasks = _serialize_final_submission_tasks(project, business_client.user.id)

    assert len(tasks) == 1
    assert [annotation['id'] for annotation in tasks[0]['annotations']] == [own_annotation.id]
    assert tasks[0]['drafts'] == [draft.id]
    assert tasks[0]['predictions'] == [prediction.id]


@pytest.mark.django_db
def test_lunor_submission_upload_is_queued_once(business_client, mocker):
    project = make_project({'challenge_id': 321, 'round': 2}, business_client.user, use_ml_backend=False)
    task = make_task({'data': {'text': 'final submission task'}}, project)
    make_annotation({'result': [], 'completed_by': business_client.user}, task.id)
    enqueue = mocker.patch('projects.api.start_job_async_or_sync')
    mocker.patch('projects.api.redis_connected', return_value=True)
    mocker.patch(
        'projects.api._request_final_submission_upload_url',
        return_value=(
            {'submissionId': 98765},
            'https://example.com/upload',
            [{'url': 'https://example.com/upload', 'key': 'asset-key'}],
        ),
    )

    payload = {
        'studio_project_id': project.id,
        'studio_user_id': business_client.user.id,
        'lunor_userId': 'quest-user-123',
    }

    first_response = business_client.post(
        '/api/lunor/submission-assets/upload/',
        data=json.dumps(payload),
        content_type='application/json',
    )
    second_response = business_client.post(
        '/api/lunor/submission-assets/upload/',
        data=json.dumps(payload),
        content_type='application/json',
    )

    assert first_response.status_code == 202
    assert first_response.json()['status'] == 'accepted'
    assert first_response.json()['lunor_submission_id'] == 98765
    assert second_response.status_code == 202
    assert second_response.json()['status'] == 'accepted'
    assert enqueue.call_count == 1


@pytest.mark.django_db
def test_lunor_submission_upload_status_includes_download_url(business_client):
    project = make_project({}, business_client.user, use_ml_backend=False)
    _set_final_submission_upload_status(
        project.id,
        business_client.user.id,
        'completed',
        success=True,
        export_id=77,
        uploaded_filename='final-submission.csv',
    )

    response = business_client.get(
        f'/api/lunor/submission-assets/upload/?studio_project_id={project.id}&studio_user_id={business_client.user.id}'
    )

    assert response.status_code == 200
    assert response.json()['status'] == 'completed'
    assert response.json()['download_url'] == f'/api/projects/{project.id}/exports/77/download?exportType=CSV'
