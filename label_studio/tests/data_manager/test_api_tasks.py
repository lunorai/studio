"""This file and its contents are licensed under the Apache License 2.0. Please see the included NOTICE for copyright information and LICENSE for a copy of the license.
"""
import json

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from projects.models import Project

from ..utils import make_annotation, make_annotator, make_prediction, make_task, project_id  # noqa


@pytest.mark.django_db
def test_views_tasks_api(business_client, project_id):
    # create
    payload = dict(project=project_id, data={'test': 1})
    response = business_client.post(
        '/api/dm/views/',
        data=json.dumps(payload),
        content_type='application/json',
    )

    assert response.status_code == 201, response.content
    view_id = response.json()['id']

    # no tasks
    response = business_client.get(f'/api/tasks?fields=all&view={view_id}')

    assert response.status_code == 200, response.content
    assert response.json()['total'] == 0
    assert len(response.json()['tasks']) == 0

    project = Project.objects.get(pk=project_id)
    task_data = {'text': 'bbb'}
    task_id = make_task({'data': task_data}, project).id

    annotation_result = {'from_name': 'my_class', 'to_name': 'text', 'type': 'choices', 'value': {'choices': ['pos']}}
    make_annotation({'result': [annotation_result]}, task_id)
    make_annotation(
        {
            'result': [annotation_result],
            'was_cancelled': True,
        },
        task_id,
    )
    prediction_result = {'from_name': 'my_class', 'to_name': 'text', 'type': 'choices', 'value': {'choices': ['pos']}}
    make_prediction(
        {
            'result': [prediction_result],
        },
        task_id,
    )

    response = business_client.get(f'/api/tasks?fields=all&view={view_id}')

    assert response.status_code == 200, response.content
    response_data = response.json()
    assert response_data['total'] == 1
    assert len(response_data['tasks']) == 1
    assert response_data['tasks'][0]['id'] == task_id
    assert response_data['tasks'][0]['data'] == task_data
    assert response_data['tasks'][0]['total_annotations'] == 1
    assert 'annotations_results' in response_data['tasks'][0]
    assert response_data['tasks'][0]['cancelled_annotations'] == 1
    assert response_data['tasks'][0]['total_predictions'] == 1
    assert 'predictions_results' in response_data['tasks'][0]

    num_anno1 = response_data['tasks'][0]['annotations'][0]['id']
    num_anno2 = response_data['tasks'][0]['annotations'][1]['id']
    num_pred = response_data['tasks'][0]['predictions'][0]['id']

    # delete annotations and check counters

    business_client.delete(f'/api/annotations/{num_anno1}')
    business_client.delete(f'/api/annotations/{num_anno2}')

    response = business_client.get(f'/api/tasks?fields=all&view={view_id}')
    assert response.status_code == 200, response.content
    response_data = response.json()
    assert response_data['tasks'][0]['cancelled_annotations'] == 0
    assert response_data['tasks'][0]['total_annotations'] == 0

    # delete prediction and check counters
    business_client.delete(f'/api/predictions/{num_pred}')

    response = business_client.get(f'/api/tasks?fields=all&view={view_id}')
    assert response.status_code == 200, response.content
    response_data = response.json()
    assert response_data['tasks'][0]['cancelled_annotations'] == 0
    assert response_data['tasks'][0]['total_annotations'] == 0
    assert response_data['tasks'][0]['total_predictions'] == 0


@pytest.mark.parametrize(
    'tasks_count, annotations_count, predictions_count',
    [
        [0, 0, 0],
        [1, 0, 0],
        [1, 1, 1],
        [2, 2, 2],
    ],
)
@pytest.mark.django_db
def test_views_total_counters(tasks_count, annotations_count, predictions_count, business_client, project_id):
    # create
    payload = dict(project=project_id, data={'test': 1})
    response = business_client.post(
        '/api/dm/views/',
        data=json.dumps(payload),
        content_type='application/json',
    )

    assert response.status_code == 201, response.content
    view_id = response.json()['id']

    project = Project.objects.get(pk=project_id)
    for _ in range(0, tasks_count):
        task_id = make_task({'data': {}}, project).id
        print('TASK_ID: %s' % task_id)
        for _ in range(0, annotations_count):
            make_annotation({'result': []}, task_id)

        for _ in range(0, predictions_count):
            make_prediction({'result': []}, task_id)

    response = business_client.get(f'/api/tasks?fields=all&view={view_id}')

    response_data = response.json()

    assert response_data['total'] == tasks_count, response_data
    assert response_data['total_annotations'] == tasks_count * annotations_count, response_data
    assert response_data['total_predictions'] == tasks_count * predictions_count, response_data


@pytest.mark.django_db
def test_views_tasks_api_fast_counts_use_task_counters(business_client, project_id):
    payload = dict(project=project_id, data={'test': 1})
    response = business_client.post(
        '/api/dm/views/',
        data=json.dumps(payload),
        content_type='application/json',
    )

    assert response.status_code == 201, response.content
    view_id = response.json()['id']

    project = Project.objects.get(pk=project_id)
    task_ids = [make_task({'data': {'text': f'task-{i}'}}, project).id for i in range(2)]

    make_annotation({'result': []}, task_ids[0])
    make_annotation({'result': [], 'was_cancelled': True}, task_ids[0])
    make_annotation({'result': []}, task_ids[1])

    make_prediction({'result': []}, task_ids[0])
    make_prediction({'result': []}, task_ids[1])
    make_prediction({'result': []}, task_ids[1])

    url = (
        f'/api/tasks?fields=all&view={view_id}'
        '&include_annotation_counts=1'
        '&include_prediction_counts=1'
        '&include_user_annotation_counts=0'
    )

    with CaptureQueriesContext(connection) as queries:
        response = business_client.get(url)

    assert response.status_code == 200, response.content
    response_data = response.json()
    assert response_data['total_annotations'] == 2
    assert response_data['total_predictions'] == 3

    count_queries = [query['sql'].lower() for query in queries.captured_queries if 'count(' in query['sql'].lower()]
    assert not any('task_annotation' in query for query in count_queries), count_queries
    assert not any('task_prediction' in query for query in count_queries), count_queries


@pytest.mark.django_db
def test_views_tasks_api_fast_mode_keeps_view_filters(business_client, project_id):
    payload = {
        'project': project_id,
        'data': {
            'filters': {
                'conjunction': 'and',
                'items': [
                    {
                        'filter': 'filter:tasks:data.text',
                        'operator': 'contains',
                        'type': 'String',
                        'value': 'match',
                    }
                ],
            }
        },
    }
    response = business_client.post(
        '/api/dm/views/',
        data=json.dumps(payload),
        content_type='application/json',
    )

    assert response.status_code == 201, response.content
    view_id = response.json()['id']

    project = Project.objects.get(pk=project_id)
    matching_task = make_task({'data': {'text': 'please match me'}}, project)
    make_task({'data': {'text': 'skip this task'}}, project)

    make_annotation({'result': []}, matching_task.id)
    make_prediction({'result': []}, matching_task.id)

    response = business_client.get(
        f'/api/tasks?page=1&page_size=15'
        f'&include_annotation_counts=true'
        f'&include_user_annotation_counts=true'
        f'&include_prediction_counts=true'
        f'&optimize_summary_counts=true'
        f'&view={view_id}&project={project_id}'
    )

    assert response.status_code == 200, response.content
    response_data = response.json()
    assert response_data['total'] == 1, response_data
    assert response_data['total_annotations'] == 1, response_data
    assert response_data['total_predictions'] == 1, response_data
    assert response_data['total_user_annotations'] == 0, response_data
    assert [task['id'] for task in response_data['tasks']] == [matching_task.id], response_data


@pytest.mark.django_db
def test_views_tasks_api_fast_mode_keeps_exact_total_user_annotations(business_client, project_id):
    payload = {
        'project': project_id,
        'data': {
            'filters': {
                'conjunction': 'and',
                'items': [
                    {
                        'filter': 'filter:tasks:data.text',
                        'operator': 'contains',
                        'type': 'String',
                        'value': 'mine',
                    }
                ],
            }
        },
    }
    response = business_client.post(
        '/api/dm/views/',
        data=json.dumps(payload),
        content_type='application/json',
    )

    assert response.status_code == 201, response.content
    view_id = response.json()['id']

    project = Project.objects.get(pk=project_id)
    first_task = make_task({'data': {'text': 'mine one'}}, project)
    second_task = make_task({'data': {'text': 'mine two'}}, project)
    make_task({'data': {'text': 'not mine'}}, project)

    make_annotation({'result': [], 'completed_by': business_client.user}, first_task.id)
    make_annotation({'result': [], 'completed_by': business_client.user}, second_task.id)

    response = business_client.get(
        f'/api/tasks?page=1&page_size=1'
        f'&include_annotation_counts=true'
        f'&include_user_annotation_counts=true'
        f'&include_prediction_counts=true'
        f'&optimize_summary_counts=true'
        f'&view={view_id}&project={project_id}'
    )

    assert response.status_code == 200, response.content
    response_data = response.json()
    assert response_data['total_user_annotations'] == 2, response_data
    assert len(response_data['tasks']) == 1, response_data


@pytest.mark.django_db
def test_views_tasks_api_returns_embedded_updated_by_user(business_client, project_id):
    payload = dict(project=project_id, data={'test': 1})
    response = business_client.post(
        '/api/dm/views/',
        data=json.dumps(payload),
        content_type='application/json',
    )

    assert response.status_code == 201, response.content
    view_id = response.json()['id']

    project = Project.objects.get(pk=project_id)
    task = make_task({'data': {'text': 'updated by me'}}, project)
    make_annotation({'result': [], 'completed_by': business_client.user}, task.id)

    response = business_client.get(f'/api/tasks?fields=all&dm_fast=0&view={view_id}')

    assert response.status_code == 200, response.content
    response_data = response.json()
    assert len(response_data['tasks']) == 1, response_data

    updated_by = response_data['tasks'][0]['updated_by']

    assert updated_by == [
        {
            'user_id': business_client.user.id,
            'first_name': business_client.user.first_name or '',
            'last_name': business_client.user.last_name or '',
            'username': business_client.user.username or '',
            'email': business_client.user.email or '',
            'last_activity': business_client.user.last_activity.isoformat() if business_client.user.last_activity else '',
            'avatar': business_client.user.avatar.url if business_client.user.avatar else None,
            'initials': business_client.user.get_initials(False),
            'lunor_userId': business_client.user.lunor_userId or '',
        }
    ]


@pytest.mark.django_db
def test_next_task_all_mode_resumes_from_current_users_progress(project_id):
    project = Project.objects.get(pk=project_id)
    task = make_task({'data': {'text': 'resume me'}}, project)

    ann1 = make_annotator({'email': 'resume-ann1@example.com'}, project, login=True)
    ann2 = make_annotator({'email': 'resume-ann2@example.com'}, project, login=True)

    make_annotation({'result': [], 'completed_by': ann1.annotator}, task.id)

    default_response = ann2.post('/api/dm/actions/?project={}&id=next_task'.format(project_id), content_type='application/json')
    assert default_response.status_code == 404, default_response.content

    all_mode_response = ann2.post(
        '/api/dm/actions/?project={}&id=next_task'.format(project_id),
        data=json.dumps({'label_stream_mode': 'all'}),
        content_type='application/json',
    )
    assert all_mode_response.status_code == 200, all_mode_response.content
    assert all_mode_response.json()['id'] == task.id


@pytest.mark.django_db
def test_next_task_all_mode_skips_tasks_locked_by_other_users(project_id):
    project = Project.objects.get(pk=project_id)
    first_task = make_task({'data': {'text': 'locked by another user'}}, project)
    second_task = make_task({'data': {'text': 'available for me'}}, project)

    ann1 = make_annotator({'email': 'resume-lock-ann1@example.com'}, project, login=True)
    ann2 = make_annotator({'email': 'resume-lock-ann2@example.com'}, project, login=True)

    first_task.set_lock(ann1.annotator)

    all_mode_response = ann2.post(
        '/api/dm/actions/?project={}&id=next_task'.format(project_id),
        data=json.dumps({'label_stream_mode': 'all'}),
        content_type='application/json',
    )

    assert all_mode_response.status_code == 200, all_mode_response.content
    assert all_mode_response.json()['id'] == second_task.id


@pytest.mark.django_db
def test_project_state_returns_user_queue_stats(business_client, project_id):
    project = Project.objects.get(pk=project_id)
    first_task = make_task({'data': {'text': 'task-1'}}, project)
    second_task = make_task({'data': {'text': 'task-2'}}, project)

    make_annotation({'result': [], 'completed_by': business_client.user}, first_task.id)
    make_annotation({'result': [], 'completed_by': business_client.user}, second_task.id)

    response = business_client.get(f'/api/dm/project/?project={project_id}')

    assert response.status_code == 200, response.content
    response_data = response.json()
    assert response_data['task_count'] == 2, response_data
    assert response_data['queue_total'] == 2, response_data
    assert response_data['queue_done'] == 2, response_data
    assert response_data['queue_left'] == 0, response_data
    assert response_data['my_annotation_count'] == 2, response_data
