"""
This file and its contents are licensed under the Apache License 2.0. Please see the included NOTICE for copyright information and LICENSE for a copy of the license.
"""

import logging
import os
import pathlib
import shutil
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit
import ujson as json

from core.filters import ListFilter
from core.feature_flags import flag_set
from core.label_config import config_essential_data_has_changed
from core.mixins import GetParentObjectMixin
from core.permissions import ViewClassPermission, all_permissions
from core.redis import redis_connected, start_job_async_or_sync
from core.utils.cache import bump_project_cache_version, get_project_cache_version
from core.utils.common import batched_iterator, paginator, paginator_help, temporary_disconnect_all_signals
from core.utils.exceptions import LabelStudioDatabaseException, ProjectExistException
from core.utils.filterset_to_openapi_params import filterset_to_openapi_params
from core.utils.io import find_dir, find_file, get_all_files_from_dir, get_temp_dir, read_yaml
from core.utils.params import bool_from_request
from core.utils.serializer_to_openapi_params import serializer_to_openapi_params
from data_manager.functions import filters_ordering_selected_items_exist, get_prepared_queryset
from data_export.serializers import ExportDataSerializer
from django.conf import settings
from django.core.cache import cache
from django.core.files import File
from django.core.files import temp as tempfile
from django.db import IntegrityError
from django.db.models import Count, F, Prefetch, Q, Sum
from django.http import Http404
from django.utils.decorators import method_decorator
from django_filters import CharFilter, FilterSet
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, OpenApiResponse, extend_schema
from label_studio_sdk.label_interface.interface import LabelInterface
from ml.serializers import MLBackendSerializer
from projects.functions.next_task import get_next_task
from projects.functions.user_batch_assignment import get_or_create_user_assignment
from projects.functions.stream_history import get_label_stream_history
from projects.functions.utils import recalculate_created_annotations_and_labels_from_scratch
from projects.models import Project, ProjectImport, ProjectManager, ProjectReimport, ProjectSummary, FinalSubmission
from projects.serializers import (
    GetFieldsSerializer,
    ProjectCountsSerializer,
    ProjectImportSerializer,
    ProjectLabelConfigSerializer,
    ProjectModelVersionExtendedSerializer,
    ProjectModelVersionParamsSerializer,
    ProjectReimportSerializer,
    ProjectSerializer,
    ProjectSummarySerializer,
)
from rest_framework import filters, generics, status
from rest_framework.exceptions import NotFound
from rest_framework.exceptions import ValidationError as RestValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework import serializers
import requests
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.views import APIView, exception_handler
from tasks.models import Annotation, AnnotationDraft, Prediction, Task
from tasks.serializers import (
    NextTaskSerializer,
    TaskSerializer,
    TaskSimpleSerializer,
    TaskWithAnnotationsAndPredictionsAndDraftsSerializer,
)
from users.models import User
from users.serializers import UserSimpleSerializer
from webhooks.models import WebhookAction
from webhooks.utils import api_webhook, api_webhook_for_delete, emit_webhooks_for_instance

from label_studio.core.utils.common import load_func

logger = logging.getLogger(__name__)

ProjectImportPermission = load_func(settings.PROJECT_IMPORT_PERMISSION)
FINAL_SUBMISSION_CHECK_CACHE_TIMEOUT = 60
FINAL_SUBMISSION_UPLOAD_CACHE_TIMEOUT = 60 * 60 * 24
FINAL_SUBMISSION_UPLOAD_ACTIVE_STATUSES = {
    'accepted',
    'queued',
    'exporting',
    'converting',
    'requesting_upload_url',
    'uploading',
    'finalizing',
}
FINAL_SUBMISSION_UPLOAD_BLOCKING_STATUSES = FINAL_SUBMISSION_UPLOAD_ACTIVE_STATUSES | {'completed'}


def _get_final_submission_file_copy_buffer_size():
    return int(getattr(settings, 'FINAL_SUBMISSION_FILE_COPY_BUFFER_SIZE', 8 * 1024 * 1024))


def _get_final_submission_export_batch_size(project):
    configured = int(getattr(settings, 'FINAL_SUBMISSION_EXPORT_BATCH_SIZE', 5000))
    project_batch_size = project.get_task_batch_size()
    if project_batch_size < configured // 4:
        return max(project_batch_size, 1)
    return configured


def _final_submission_export_serializer_kwargs():
    options = _final_submission_serialization_options()
    kwargs = {
        'many': True,
        'context': {'interpolate_key_frames': options.get('interpolate_key_frames', False)},
    }
    if options.get('include_annotation_history') is False:
        kwargs['omit'] = ['annotations.history']
    return kwargs


def _normalize_submission_scope_value(value):
    return None if value in ('', None) else value


def _final_submission_check_cache_key(project_id, user_id):
    version = get_project_cache_version(project_id)
    return f'final_submission_check:{project_id}:{user_id}:v{version}'


def _final_submission_upload_cache_key(project_id, user_id):
    version = get_project_cache_version(project_id)
    return f'final_submission_upload:{project_id}:{user_id}:v{version}'


def _final_submission_upload_info_cache_key(project_id, user_id):
    version = get_project_cache_version(project_id)
    return f'final_submission_upload_info:{project_id}:{user_id}:v{version}'


def _final_submission_export_title(user_id):
    return f'Final submission (user {user_id})'


def _final_submission_task_filter_options(studio_user_id):
    return {
        'annotated': 'only',
        'only_with_annotations': True,
        'completed_by': studio_user_id,
    }


def _final_submission_annotation_filter_options(studio_user_id):
    return {
        'usual': True,
        'completed_by': studio_user_id,
    }


def _final_submission_serialization_options():
    return {
        'include_annotation_history': False,
        'interpolate_key_frames': False,
    }


def _augment_final_submission_upload_payload(payload, project_id):
    if not isinstance(payload, dict):
        return {'status': 'idle', 'percent': 0, 'message': 'Ready to submit final annotations.'}

    response_payload = dict(payload)
    export_id = response_payload.get('export_id')
    if export_id:
        response_payload['download_url'] = f'/api/projects/{project_id}/exports/{export_id}/download?exportType=CSV'
    lunor_submission_id = response_payload.get('lunor_submission_id')
    if lunor_submission_id is not None and 'submission_id' not in response_payload:
        response_payload['submission_id'] = lunor_submission_id
    return response_payload


def _get_final_submission_upload_status(project_id, user_id):
    payload = cache.get(_final_submission_upload_cache_key(project_id, user_id))
    return _augment_final_submission_upload_payload(payload, project_id)


def _set_final_submission_upload_status(project_id, user_id, status_value, **extra):
    existing_payload = cache.get(_final_submission_upload_cache_key(project_id, user_id)) or {}
    payload = {**existing_payload, 'status': status_value, **extra}
    cache.set(
        _final_submission_upload_cache_key(project_id, user_id),
        payload,
        FINAL_SUBMISSION_UPLOAD_CACHE_TIMEOUT,
    )
    return _augment_final_submission_upload_payload(payload, project_id)


def _build_final_submission_status(status_value, percent, message, **extra):
    return {
        'percent': max(0, min(100, int(percent))),
        'message': message,
        'status': status_value,
        **extra,
    }


def _set_final_submission_stage(project_id, user_id, status_value, percent, message, **extra):
    return _set_final_submission_upload_status(
        project_id,
        user_id,
        status_value,
        percent=max(0, min(100, int(percent))),
        message=message,
        **extra,
    )


def _final_submission_export_message(processed_tasks, total_tasks):
    if total_tasks <= 0:
        return 'Preparing filtered annotation export.'
    return f'Preparing filtered annotation export ({processed_tasks:,} / {total_tasks:,} tasks).'


def _get_final_submission_graphql_endpoint():
    runtime_graphql = getattr(settings, 'GRAPHQL_ENDPOINT', None)
    return _resolve_container_localhost_url(
        runtime_graphql or os.environ.get('GRAPHQL_ENDPOINT') or 'https://prod.100protocol.com/'
    )


def _build_final_submission_filename(project_id, studio_user_id):
    return f'final-submission-project-{project_id}-user-{studio_user_id}.csv'


def _set_final_submission_reserved_upload(project_id, user_id, upload_info, upload_url, url_arr, filename):
    cache.set(
        _final_submission_upload_info_cache_key(project_id, user_id),
        {
            'upload_info': upload_info,
            'upload_url': upload_url,
            'url_arr': url_arr,
            'filename': filename,
        },
        FINAL_SUBMISSION_UPLOAD_CACHE_TIMEOUT,
    )


def _get_final_submission_reserved_upload(project_id, user_id):
    reserved = cache.get(_final_submission_upload_info_cache_key(project_id, user_id))
    return reserved if isinstance(reserved, dict) else {}


def _clear_final_submission_reserved_upload(project_id, user_id):
    cache.delete(_final_submission_upload_info_cache_key(project_id, user_id))


def _verify_final_submission_eligibility(project, studio_user_id, lunor_user_id):
    if not _normalize_submission_scope_value(project.challenge_id):
        return 'Project has no challenge_id; cannot submit final annotations.'
    if not str(lunor_user_id or '').strip():
        return 'Missing Lunor user id; cannot submit final annotations.'
    has_annotations = Task.objects.filter(
        project_id=project.id,
        annotations__completed_by_id=studio_user_id,
    ).exists()
    if not has_annotations:
        return 'No submitted annotations found for this user.'
    return None


def _mark_final_submission_check_accepted(project_id, user_id, lunor_submission_id, final_submission_id=None):
    cache.set(
        _final_submission_check_cache_key(project_id, user_id),
        {
            'exists': True,
            'id': final_submission_id,
            'lunor_submission_id': lunor_submission_id,
            'status': 'accepted' if final_submission_id is None else 'completed',
        },
        FINAL_SUBMISSION_CHECK_CACHE_TIMEOUT,
    )


def _mark_final_submission_check_failed(project_id, user_id, error_message):
    cache.set(
        _final_submission_check_cache_key(project_id, user_id),
        {
            'exists': False,
            'id': None,
            'status': 'failed',
            'error': error_message,
        },
        FINAL_SUBMISSION_CHECK_CACHE_TIMEOUT,
    )


def _resolve_final_submission_upload_target(
    project_id,
    studio_user_id,
    lunor_user_id,
    challenge_id,
    round_value,
    reserved_upload=None,
    refresh=False,
):
    reserved_upload = reserved_upload or {}
    filename = reserved_upload.get('filename') or _build_final_submission_filename(project_id, studio_user_id)
    if not refresh and reserved_upload.get('upload_url') and reserved_upload.get('upload_info'):
        return (
            reserved_upload['upload_info'],
            reserved_upload['upload_url'],
            reserved_upload.get('url_arr') or [],
            filename,
        )

    upload_info, upload_url, url_arr = _request_final_submission_upload_url(
        _get_final_submission_graphql_endpoint(),
        challenge_id,
        str(lunor_user_id).strip(),
        round_value,
        filename,
    )
    _set_final_submission_reserved_upload(project_id, studio_user_id, upload_info, upload_url, url_arr, filename)
    return upload_info, upload_url, url_arr, filename


def _resolve_container_localhost_url(url_value):
    endpoint = str(url_value or '').strip()
    if not endpoint or not os.path.exists('/.dockerenv'):
        return endpoint

    try:
        parsed = urlsplit(endpoint)
    except ValueError:
        return endpoint

    if parsed.hostname not in {'localhost', '127.0.0.1', '0.0.0.0'}:
        return endpoint

    auth = ''
    if parsed.username:
        auth = parsed.username
        if parsed.password:
            auth += f':{parsed.password}'
        auth += '@'

    port = f':{parsed.port}' if parsed.port else ''
    resolved = urlunsplit(
        (
            parsed.scheme,
            f'{auth}host.docker.internal{port}',
            parsed.path,
            parsed.query,
            parsed.fragment,
        )
    )
    logger.info('Resolved container-local GraphQL endpoint %s -> %s', endpoint, resolved)
    return resolved


class _FinalSubmissionUploadProgressStream:
    def __init__(self, stream, total_bytes, progress_callback):
        self._stream = stream
        self._total_bytes = max(int(total_bytes or 0), 1)
        self._progress_callback = progress_callback
        self._bytes_read = 0
        self._last_percent = -1

    def read(self, size=-1):
        chunk = self._stream.read(size)
        if chunk:
            self._bytes_read += len(chunk)
            percent = int((self._bytes_read * 100) / self._total_bytes)
            if percent != self._last_percent:
                self._last_percent = percent
                self._progress_callback(self._bytes_read, self._total_bytes)
        return chunk

    def __getattr__(self, name):
        return getattr(self._stream, name)


def _get_existing_final_submission(project_id, user_id, challenge_id, round_value):
    return (
        FinalSubmission.objects.filter(
            project_id=project_id,
            user_id=user_id,
            challenge_id=challenge_id,
            round=round_value,
        )
        .values('id')
        .first()
    )


def _get_final_submission_tasks_queryset(project_id, studio_user_id, task_ids):
    annotation_qs = Annotation.objects.filter(project_id=project_id, completed_by_id=studio_user_id).select_related(
        'completed_by'
    )
    draft_qs = AnnotationDraft.objects.only('id', 'task_id')
    prediction_qs = Prediction.objects.only('id', 'task_id')

    return (
        Task.objects.filter(project_id=project_id, id__in=task_ids)
        .select_related('project', 'file_upload')
        .prefetch_related(
            Prefetch('annotations', queryset=annotation_qs),
            Prefetch('drafts', queryset=draft_qs),
            Prefetch('predictions', queryset=prediction_qs),
        )
        .order_by('id')
    )


def _write_final_submission_export_content(export_file, project, user, total_tasks, progress_callback=None, export_id=None):
    task_ids_qs = (
        Task.objects.filter(project_id=project.id, annotations__completed_by_id=user.id)
        .distinct()
        .order_by('id')
        .values_list('id', flat=True)
    )
    processed_tasks = 0
    batch_size = _get_final_submission_export_batch_size(project)
    serializer_kwargs = _final_submission_export_serializer_kwargs()

    export_file.write(b'[')
    first_task = True

    for task_ids_batch in batched_iterator(task_ids_qs.iterator(chunk_size=batch_size), batch_size):
        task_batch = _get_final_submission_tasks_queryset(project.id, user.id, task_ids_batch)
        serialized_tasks = ExportDataSerializer(task_batch, **serializer_kwargs).data

        for task in serialized_tasks:
            if not first_task:
                export_file.write(b',')
            export_file.write(json.dumps(task, ensure_ascii=False).encode('utf-8'))
            first_task = False

        processed_tasks += len(serialized_tasks)
        if progress_callback:
            export_percent = 10 if total_tasks <= 0 else 10 + int((processed_tasks * 50) / total_tasks)
            progress_callback(
                _build_final_submission_status(
                    'exporting',
                    export_percent,
                    _final_submission_export_message(processed_tasks, total_tasks),
                    export_id=export_id,
                    progress_current=processed_tasks,
                    progress_total=total_tasks,
                )
            )

    export_file.write(b']')
    export_file.flush()
    return processed_tasks


def _create_final_submission_export_snapshot(project, user, progress_callback=None, export_file_path=None):
    from data_export.models import Export

    export = Export.objects.create(
        title=_final_submission_export_title(user.id),
        project=project,
        created_by=user,
    )

    task_ids_qs = (
        Task.objects.filter(project_id=project.id, annotations__completed_by_id=user.id)
        .distinct()
        .order_by('id')
        .values_list('id', flat=True)
    )
    total_tasks = task_ids_qs.count()
    processed_tasks = 0

    export.status = Export.Status.IN_PROGRESS
    export.counters = {'task_number': total_tasks}
    export.save(update_fields=['status', 'counters'])

    if progress_callback:
        progress_callback(
            _build_final_submission_status(
                'exporting',
                10,
                _final_submission_export_message(0, total_tasks),
                export_id=export.id,
                progress_current=0,
                progress_total=total_tasks,
            )
        )

    try:
        if export_file_path is not None:
            export_path = pathlib.Path(export_file_path)
            export_path.parent.mkdir(parents=True, exist_ok=True)
            with open(export_path, 'wb') as export_file:
                processed_tasks = _write_final_submission_export_content(
                    export_file,
                    project,
                    user,
                    total_tasks,
                    progress_callback=progress_callback,
                    export_id=export.id,
                )
            with open(export_path, 'rb') as export_file:
                md5 = Export.eval_md5(export_file)
                export_file.seek(0)
                export.save_file(export_file, md5)
        else:
            with tempfile.NamedTemporaryFile(suffix='.export.json', dir=settings.FILE_UPLOAD_TEMP_DIR) as export_file:
                processed_tasks = _write_final_submission_export_content(
                    export_file,
                    project,
                    user,
                    total_tasks,
                    progress_callback=progress_callback,
                    export_id=export.id,
                )
                export_file.seek(0)
                md5 = Export.eval_md5(export_file)
                export_file.seek(0)
                export.save_file(export_file, md5)

        export.status = Export.Status.COMPLETED
        export.save(update_fields=['status'])
    except Exception:
        export.status = Export.Status.FAILED
        export.save(update_fields=['status'])
        raise
    finally:
        export.finished_at = datetime.now()
        export.save(update_fields=['finished_at'])

    if progress_callback:
        progress_callback(
            _build_final_submission_status(
                'exporting',
                60,
                _final_submission_export_message(processed_tasks, total_tasks),
                export_id=export.id,
                progress_current=processed_tasks,
                progress_total=total_tasks,
            )
        )

    return export


def _convert_final_submission_export_to_csv(
    export,
    project,
    user,
    hostname,
    input_file_path=None,
    work_dir=None,
    output_filename=None,
):
    from data_export.models import ConvertedFormat
    from label_studio_sdk.converter import Converter

    converted_format = ConvertedFormat.objects.create(
        export=export,
        export_type='CSV',
        project=project,
        organization=project.organization,
        created_by=user,
        status=ConvertedFormat.Status.IN_PROGRESS,
    )

    copy_buffer_size = _get_final_submission_file_copy_buffer_size()

    def _convert_in_directory(tmp_dir):
        out_dir = pathlib.Path(tmp_dir) / 'out'
        out_dir.mkdir(mode=0o700, parents=True, exist_ok=True)

        converter = Converter(
            config=project.get_parsed_config(),
            project_dir=None,
            upload_dir=out_dir,
            download_resources=False,
            access_token=project.organization.created_by.auth_token.key,
            hostname=hostname,
        )

        if input_file_path:
            source_path = pathlib.Path(input_file_path)
            input_name = source_path.name
        else:
            input_name = pathlib.Path(export.file.name).name
            source_path = pathlib.Path(tmp_dir) / input_name
            with export.file.open('rb') as source, open(source_path, 'wb') as target:
                shutil.copyfileobj(source, target, length=copy_buffer_size)

        converter.convert(source_path, out_dir, 'CSV', is_dir=False)
        output_files = get_all_files_from_dir(out_dir)
        if len(output_files) != 1:
            raise RuntimeError('CSV conversion did not produce exactly one file.')
        return output_files[0], input_name

    try:
        if work_dir:
            output_file, input_name = _convert_in_directory(work_dir)
        else:
            with get_temp_dir() as tmp_dir:
                output_file, input_name = _convert_in_directory(tmp_dir)

        output_ext = pathlib.Path(output_file).suffix or '.csv'
        if output_filename:
            stored_name = f'{project.id}/{output_filename}'
        else:
            stored_name = f'{project.id}/{pathlib.Path(input_name).stem}{output_ext}'

        with open(output_file, 'rb') as converted_stream:
            converted_format.file.save(stored_name, File(converted_stream, name=stored_name))

        converted_format.status = ConvertedFormat.Status.COMPLETED
        converted_format.save(update_fields=['file', 'status'])
        return converted_format, output_file
    except Exception:
        converted_format.status = ConvertedFormat.Status.FAILED
        converted_format.save(update_fields=['status'])
        raise


def _request_final_submission_upload_url(graphql_endpoint, challenge_id, graphql_user_id, round_value, filename):
    gql_query = (
        "query($challengeId: Int!, $userId: String!, $round: Int!, $filename: String!) {"
        "  getAnnotationUploadUrl(challengeId: $challengeId, userId: $userId, round: $round, filename: $filename) {"
        "    submissionId"
        "    urlArr { url key }"
        "  }"
        "}"
    )
    try:
        response = requests.post(
            graphql_endpoint,
            json={
                'query': gql_query,
                'variables': {
                    'challengeId': int(challenge_id),
                    'userId': graphql_user_id,
                    'round': int(round_value or 1),
                    'filename': filename,
                },
            },
            timeout=60,
        )
    except requests.RequestException as exc:
        raise RuntimeError(
            'Final submission could not reach the Quest GraphQL endpoint '
            f'({graphql_endpoint}). If you are running Docker locally, use '
            'http://host.docker.internal:5000/graphql or another container-reachable URL.'
        ) from exc
    if response.status_code >= 400:
        raise RuntimeError(f'GraphQL getAnnotationUploadUrl failed: {response.status_code}')

    payload = response.json()
    graphql_errors = payload.get('errors') or []
    if graphql_errors:
        raise RuntimeError(graphql_errors[0].get('message') or 'GraphQL getAnnotationUploadUrl failed.')
    upload_info = (payload.get('data') or {}).get('getAnnotationUploadUrl') or {}
    url_arr = upload_info.get('urlArr') or []
    upload_url = (url_arr[0] or {}).get('url') if isinstance(url_arr, list) and url_arr else None
    if not upload_url:
        raise RuntimeError('No upload URL returned from GraphQL.')
    return upload_info, upload_url, url_arr


def _upload_final_submission_csv(upload_url, converted_format, progress_callback=None, local_file_path=None):
    filename = os.path.basename(local_file_path or converted_format.file.name)
    read_timeout = int(getattr(settings, 'FINAL_SUBMISSION_UPLOAD_READ_TIMEOUT', 4 * 60 * 60))

    if local_file_path:
        file_size = os.path.getsize(local_file_path)
        file_handle = open(local_file_path, 'rb')
        should_close = True
    else:
        file_size = converted_format.file.size
        file_handle = converted_format.file.open('rb')
        should_close = False

    try:
        upload_stream = file_handle
        if progress_callback:
            upload_stream = _FinalSubmissionUploadProgressStream(file_handle, file_size, progress_callback)
        response = requests.put(
            upload_url,
            data=upload_stream,
            headers={
                'Content-Type': 'text/csv',
                'Content-Length': str(file_size),
            },
            timeout=(60, read_timeout),
        )
    finally:
        if should_close:
            file_handle.close()

    if response.status_code >= 400:
        raise RuntimeError(f'Upload failed: {response.status_code}')
    return filename


def _upload_final_submission_csv_with_retry(
    project_id,
    studio_user_id,
    lunor_user_id,
    challenge_id,
    round_value,
    upload_url,
    converted_format,
    local_file_path,
    progress_callback=None,
):
    try:
        uploaded_filename = _upload_final_submission_csv(
            upload_url,
            converted_format,
            progress_callback=progress_callback,
            local_file_path=local_file_path,
        )
    except RuntimeError:
        logger.warning(
            'Final submission upload failed for project_id=%s studio_user_id=%s; refreshing upload URL.',
            project_id,
            studio_user_id,
        )
        upload_info, refreshed_upload_url, url_arr, _filename = _resolve_final_submission_upload_target(
            project_id,
            studio_user_id,
            lunor_user_id,
            challenge_id,
            round_value,
            refresh=True,
        )
        uploaded_filename = _upload_final_submission_csv(
            refreshed_upload_url,
            converted_format,
            progress_callback=progress_callback,
            local_file_path=local_file_path,
        )
        return uploaded_filename, upload_info, url_arr

    reserved = _get_final_submission_reserved_upload(project_id, studio_user_id)
    return uploaded_filename, reserved.get('upload_info') or {}, reserved.get('url_arr') or []


def _update_final_submission_asset_list(
    graphql_endpoint, upload_info, asset_keys, challenge_id, round_value, graphql_user_id
):
    update_mutation = (
        "mutation UpdateSubmissionAssetList($submissionId: Int, $challengeId: Int, $round: Int, $userId: String!, $asset_list: [String!]!) {"
        "  updateSubmissionAssetList("
        "    submissionId: $submissionId"
        "    challengeId: $challengeId"
        "    round: $round"
        "    userId: $userId"
        "    asset_list: $asset_list"
        "  )"
        "}"
    )
    try:
        response = requests.post(
            graphql_endpoint,
            json={
                'query': update_mutation,
                'variables': {
                    'submissionId': upload_info.get('submissionId'),
                    'challengeId': int(challenge_id),
                    'round': int(round_value or 1),
                    'userId': graphql_user_id,
                    'asset_list': asset_keys,
                },
            },
            timeout=60,
        )
    except requests.RequestException as exc:
        raise RuntimeError(
            'Final submission uploaded the CSV but could not finalize it on the Quest platform '
            f'because the GraphQL endpoint {graphql_endpoint} was unreachable.'
        ) from exc
    if response.status_code >= 400:
        raise RuntimeError(f'GraphQL updateSubmissionAssetList failed: {response.status_code}')
    payload = response.json()
    graphql_errors = payload.get('errors') or []
    if graphql_errors:
        raise RuntimeError(graphql_errors[0].get('message') or 'GraphQL updateSubmissionAssetList failed.')
    return response


def _serialize_final_submission_tasks(project, studio_user_id):
    task_ids = list(
        Task.objects.filter(project_id=project.id, annotations__completed_by_id=studio_user_id)
        .distinct()
        .order_by('id')
        .values_list('id', flat=True)
    )
    tasks_qs = _get_final_submission_tasks_queryset(project.id, studio_user_id, task_ids)

    return ExportDataSerializer(
        tasks_qs,
        many=True,
        context={'interpolate_key_frames': False},
    ).data

_result_schema = {
    'title': 'Labeling result',
    'description': 'Labeling result (choices, labels, bounding boxes, etc.)',
    'type': 'object',
    'properties': {
        'from_name': {
            'type': 'string',
            'description': 'The name of the labeling tag from the project config',
        },
        'to_name': {
            'type': 'string',
            'description': 'The name of the labeling tag from the project config',
        },
        'value': {
            'type': 'object',
            'description': 'Labeling result value. Format depends on chosen ML backend',
        },
    },
    'example': {'from_name': 'image_class', 'to_name': 'image', 'value': {'labels': ['Cat']}},
}

_task_data_schema = {
    'title': 'Task data',
    'description': 'Task data',
    'type': 'object',
    'example': {'id': 1, 'my_image_url': '/static/samples/kittens.jpg'},
}


class ProjectListPagination(PageNumberPagination):
    page_size = 30
    page_size_query_param = 'page_size'
    max_page_size = 100


class ProjectFilterSet(FilterSet):
    ids = ListFilter(field_name='id', lookup_expr='in')
    title = CharFilter(field_name='title', lookup_expr='icontains')

# Place UpdateParticipantsAPI after all imports

class UpdateParticipantsAPI(APIView):
    permission_classes = [AllowAny]  # Allow any request without authentication
    
    def post(self, request):
        challenge_id = request.data.get('challenge_id')
        round_value = request.data.get('round')
        participant = request.data.get('participant')  # Single participant string

        # Log received data and types for debugging
        print(f"Challenge ID: {challenge_id} (type: {type(challenge_id)})")
        print(f"Round: {round_value} (type: {type(round_value)})")
        print(f"Participant: {participant} (type: {type(participant)})")

        # Ensure challenge_id and round_value are strings (to match DB text fields)
        if challenge_id is not None:
            challenge_id = str(challenge_id)
        if round_value is not None:
            round_value = str(round_value)  # Explicit cast to string

        # Validate participant presence and type
        if not participant or not isinstance(participant, str):
            return Response({'error': 'Missing or invalid participant'}, status=status.HTTP_400_BAD_REQUEST)

        # Query the project using string values to avoid type error
        project = Project.objects.filter(challenge_id=challenge_id, round=round_value).first()
        if not project:
            return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)

        # Initialize participants list if None, empty, or not a list
        current_participants = project.participants
        if not isinstance(current_participants, list):
            current_participants = []

        # Append new participant if not already in the list
        if participant not in current_participants:
            current_participants.append(participant)

        # Save changes
        project.participants = current_participants
        project.save()

        return Response({'success': True, 'participants': project.participants})


class UpdateChallengeStatusAPI(APIView):
    permission_classes = [AllowAny]  # Allow any request without authentication

    def post(self, request):
        challenge_id = request.data.get('challenge_id')
        round_value = request.data.get('round')
        status_value = request.data.get('challenge_status')  # can be bool, int, or string

        print(f"Challenge ID: {challenge_id} (type: {type(challenge_id)})")
        print(f"Round: {round_value} (type: {type(round_value)})")
        print(f"Challenge Status: {status_value} (type: {type(status_value)})")

        if challenge_id is not None:
            challenge_id = str(challenge_id)
        if round_value is not None:
            round_value = str(round_value)

        def parse_bool(value):
            if isinstance(value, bool):
                return value
            if isinstance(value, (int,)):
                return value == 1
            if isinstance(value, str):
                lowered = value.strip().lower()
                if lowered in {'true', '1', 'yes', 'y'}:
                    return True
                if lowered in {'false', '0', 'no', 'n'}:
                    return False
            return None

        parsed_status = parse_bool(status_value)
        if parsed_status is None:
            return Response({'error': 'Missing or invalid challenge_status, expected boolean-like value'}, status=status.HTTP_400_BAD_REQUEST)

        project = Project.objects.filter(challenge_id=challenge_id, round=round_value).first()
        if not project:
            return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)

        project.challenge_status = parsed_status
        project.save(update_fields=['challenge_status'])

        return Response({'success': True, 'challenge_status': project.challenge_status})


class ProjectUserTasksAPI(APIView):
    """
    Return the fixed 10–20 task batch assigned to the requesting user for a project.
    This includes tasks even if the user has already annotated them.
    """

    permission_classes = [AllowAny]

    def get(self, request, pk):
        try:
            project = Project.objects.get(pk=pk)
        except Project.DoesNotExist:
            raise NotFound(detail='Project not found')

        user = request.user
        if not user or not user.is_authenticated:
            # If you plan to use anonymous auth, adapt this
            return Response({'detail': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)

        assignment = get_or_create_user_assignment(user, project)

        if assignment is None:
            # No batch size configured: fall back to default ordering
            # (here we simply return all project tasks ordered by id,
            #  but you can adapt this to mirror Data Manager ordering if needed)
            tasks_qs = Task.objects.filter(project=project).order_by('id')
        else:
            tasks_qs = assignment.tasks.all().order_by('id')

        serializer = TaskSimpleSerializer(tasks_qs, many=True)
        return Response(serializer.data)

@method_decorator(
    name='get',
    decorator=extend_schema(
        tags=['Projects'],
        summary='List your projects',
        description="""
    Return a list of the projects that you've created.

    To perform most tasks with the Label Studio API, you must specify the project ID, sometimes referred to as the `pk`.
    To retrieve a list of your Label Studio projects, update the following command to match your own environment.
    Replace the domain name, port, and authorization token, then run the following from the command line:
    ```bash
    curl -X GET {}/api/projects/ -H 'Authorization: Token abc123'
    ```
    """.format(
            settings.HOSTNAME or 'https://localhost:8080'
        ),
        parameters=[
            *serializer_to_openapi_params(GetFieldsSerializer),
            *filterset_to_openapi_params(ProjectFilterSet),
        ],
        extensions={
            'x-fern-sdk-group-name': 'projects',
            'x-fern-sdk-method-name': 'counts',
            'x-fern-audiences': ['public'],
            'x-fern-pagination': {
                'offset': '$request.page',
                'results': '$response.results',
            },
        },
    ),
)
@method_decorator(
    name='post',
    decorator=extend_schema(
        tags=['Projects'],
        summary='Create new project',
        description="""
    Create a project and set up the labeling interface in Label Studio using the API.

    ```bash
    curl -H Content-Type:application/json -H 'Authorization: Token abc123' -X POST '{}/api/projects' \
    --data '{{"title": "My project", "label_config": "<View></View>"}}'
    ```
    """.format(
            settings.HOSTNAME or 'https://localhost:8080'
        ),
        request=ProjectSerializer,
        extensions={
            'x-fern-sdk-group-name': 'projects',
            'x-fern-sdk-method-name': 'create',
            'x-fern-audiences': ['public'],
        },
    ),
)
class ProjectListAPI(generics.ListCreateAPIView):
    FAST_COUNTER_FIELDS = {
        'task_number',
        'finished_task_number',
        'total_annotations_number',
        'total_predictions_number',
        'skipped_annotations_number',
    }

    parser_classes = (JSONParser, FormParser, MultiPartParser)
    serializer_class = ProjectSerializer
    filter_backends = [filters.OrderingFilter, DjangoFilterBackend]
    filterset_class = ProjectFilterSet
    permission_required = ViewClassPermission(
        GET=all_permissions.projects_view,
        POST=all_permissions.projects_create,
    )
    pagination_class = ProjectListPagination

    def _is_dm_fast(self):
        default_fast = flag_set('fflag_fix_back_plt_811_projects_pagination_01072025_short', user=self.request.user)
        return bool_from_request(self.request.query_params, 'dm_fast', default_fast)

    @staticmethod
    def _attach_page_counts(projects, fields):
        project_ids = [p.id for p in projects]
        if not project_ids:
            return

        task_stats = {
            row['project_id']: row
            for row in Task.objects.filter(project_id__in=project_ids)
            .values('project_id')
            .annotate(
                task_number=Count('id'),
                finished_task_number=Count('id', filter=Q(is_labeled=True)),
                total_annotations_number=Sum('total_annotations'),
                # total_predictions_number=Sum('total_predictions'),
                skipped_annotations_number=Sum('cancelled_annotations'),
            )
        }

        for project in projects:
            stats = task_stats.get(project.id) or {}
            for field in fields:
                setattr(project, field, stats.get(field, 0) or 0)

    def get_queryset(self):
        serializer = GetFieldsSerializer(data=self.request.query_params)
        serializer.is_valid(raise_exception=True)
        requested_fields = serializer.validated_data.get('include')
        self._requested_include_fields = requested_fields

        dm_fast = self._is_dm_fast()
        requested_set = set(requested_fields or [])
        if requested_fields is None:
            self._page_counter_fields = set(self.FAST_COUNTER_FIELDS) if dm_fast else set()
        else:
            self._page_counter_fields = self.FAST_COUNTER_FIELDS.intersection(requested_set) if dm_fast else set()

        fields = requested_fields
        if dm_fast:
            if fields is None:
                fields = []
            else:
                fields = [f for f in fields if f not in self.FAST_COUNTER_FIELDS]
        filter = serializer.validated_data.get('filter')
        projects = Project.objects.filter(organization=self.request.user.active_organization).order_by(
            F('pinned_at').desc(nulls_last=True), '-created_at'
        )
        # Apply backend visibility rules to mirror frontend visibleProjects logic
        # Owners (organization creators) can see all projects
        user = self.request.user
        active_org = getattr(user, 'active_organization', None)
        is_owner = bool(active_org and active_org.created_by_id == user.id)
        if not is_owner:
            # Non-owners: only active challenges where user's lunor_userId is in participants
            lunor_user_id = getattr(user, 'lunor_userId', None)
            # If lunor_userId is missing, return empty queryset for non-owners
            if lunor_user_id:
                projects = projects.filter(challenge_status=True, participants__contains=[lunor_user_id])
            else:
                projects = projects.none()
        if filter in ['pinned_only', 'exclude_pinned']:
            projects = projects.filter(pinned_at__isnull=filter == 'exclude_pinned')
        return ProjectManager.with_counts_annotate(projects, fields=fields).select_related('created_by')

    def get_serializer_context(self):
        context = super(ProjectListAPI, self).get_serializer_context()
        context['created_by'] = self.request.user
        context['dm_fast'] = self._is_dm_fast()
        return context

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        project_list = page if page is not None else queryset

        if self._is_dm_fast() and getattr(self, '_page_counter_fields', None):
            self._attach_page_counts(project_list, self._page_counter_fields)

        serializer = self.get_serializer(project_list, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    def perform_create(self, ser):
        try:
            ser.save(organization=self.request.user.active_organization)
        except IntegrityError as e:
            if str(e) == 'UNIQUE constraint failed: project.title, project.created_by_id':
                raise ProjectExistException(
                    'Project with the same name already exists: {}'.format(ser.validated_data.get('title', ''))
                )
            raise LabelStudioDatabaseException('Database error during project creation. Try again.')

    def get(self, request, *args, **kwargs):
        return super(ProjectListAPI, self).get(request, *args, **kwargs)

    @api_webhook(WebhookAction.PROJECT_CREATED)
    def post(self, request, *args, **kwargs):
        return super(ProjectListAPI, self).post(request, *args, **kwargs)


@method_decorator(
    name='get',
    decorator=extend_schema(
        tags=['Projects'],
        summary="List projects' counts",
        parameters=[
            *serializer_to_openapi_params(GetFieldsSerializer),
            *filterset_to_openapi_params(ProjectFilterSet),
        ],
        description='Returns a list of projects with their counts. For example, task_number which is the total task number in project',
        extensions={
            'x-fern-sdk-group-name': 'projects',
            'x-fern-sdk-method-name': 'list_counts',
            'x-fern-audiences': ['public'],
        },
    ),
)
class ProjectCountsListAPI(generics.ListAPIView):
    serializer_class = ProjectCountsSerializer
    filterset_class = ProjectFilterSet
    permission_required = ViewClassPermission(
        GET=all_permissions.projects_view,
    )
    pagination_class = ProjectListPagination

    def get_queryset(self):
        serializer = GetFieldsSerializer(data=self.request.query_params)
        serializer.is_valid(raise_exception=True)
        fields = serializer.validated_data.get('include')
        projects = Project.objects.with_counts(fields=fields).filter(organization=self.request.user.active_organization)
        # Apply same visibility filtering as in ProjectListAPI
        user = self.request.user
        active_org = getattr(user, 'active_organization', None)
        is_owner = bool(active_org and active_org.created_by_id == user.id)
        if not is_owner:
            lunor_user_id = getattr(user, 'lunor_userId', None)
            if lunor_user_id:
                projects = projects.filter(challenge_status=True, participants__contains=[lunor_user_id])
            else:
                projects = projects.none()
        return projects


@method_decorator(
    name='get',
    decorator=extend_schema(
        tags=['Projects'],
        summary='Get project by ID',
        description='Retrieve information about a project by project ID.',
        responses={
            '200': OpenApiResponse(
                description='Project information',
                response=ProjectSerializer,
                examples=[
                    OpenApiExample(
                        name='response',
                        value={
                            'id': 1,
                            'title': 'My project',
                            'description': 'My first project',
                            'label_config': '<View>[...]</View>',
                            'expert_instruction': 'Label all cats',
                            'show_instruction': True,
                            'show_skip_button': True,
                            'enable_empty_annotation': True,
                            'show_annotation_history': True,
                            'organization': 1,
                            'color': '#FF0000',
                            'maximum_annotations': 1,
                            'is_published': True,
                            'model_version': '1.0.0',
                            'is_draft': False,
                            'created_by': {
                                'id': 1,
                                'first_name': 'Jo',
                                'last_name': 'Doe',
                                'email': 'manager@humansignal.com',
                            },
                            'created_at': '2023-08-24T14:15:22Z',
                            'min_annotations_to_start_training': 0,
                            'start_training_on_annotation_update': True,
                            'show_collab_predictions': True,
                            'num_tasks_with_annotations': 10,
                            'task_number': 100,
                            'useful_annotation_number': 10,
                            'ground_truth_number': 5,
                            'skipped_annotations_number': 0,
                            'total_annotations_number': 10,
                            'total_predictions_number': 0,
                            'sampling': 'Sequential sampling',
                            'show_ground_truth_first': True,
                            'show_overlap_first': True,
                            'overlap_cohort_percentage': 100,
                            'task_data_login': 'user',
                            'task_data_password': 'secret',
                            'control_weights': {},
                            'parsed_label_config': '{"tag": {...}}',
                            'evaluate_predictions_automatically': False,
                            'config_has_control_tags': True,
                            'skip_queue': 'REQUEUE_FOR_ME',
                            'reveal_preannotations_interactively': True,
                            'pinned_at': '2023-08-24T14:15:22Z',
                            'finished_task_number': 10,
                            'queue_total': 10,
                            'queue_done': 100,
                        },
                        media_type='application/json',
                    )
                ],
            )
        },
        extensions={
            'x-fern-sdk-group-name': 'projects',
            'x-fern-sdk-method-name': 'get',
            'x-fern-audiences': ['public'],
        },
    ),
)
@method_decorator(
    name='delete',
    decorator=extend_schema(
        tags=['Projects'],
        summary='Delete project',
        description='Delete a project by specified project ID.',
        extensions={
            'x-fern-sdk-group-name': 'projects',
            'x-fern-sdk-method-name': 'delete',
            'x-fern-audiences': ['public'],
        },
    ),
)
@method_decorator(
    name='patch',
    decorator=extend_schema(
        tags=['Projects'],
        summary='Update project',
        description='Update the project settings for a specific project.',
        request=ProjectSerializer,
        extensions={
            'x-fern-sdk-group-name': 'projects',
            'x-fern-sdk-method-name': 'update',
            'x-fern-audiences': ['public'],
        },
    ),
)
class ProjectAPI(generics.RetrieveUpdateDestroyAPIView):
    parser_classes = (JSONParser, FormParser, MultiPartParser)
    queryset = Project.objects.with_counts()
    permission_required = ViewClassPermission(
        GET=all_permissions.projects_view,
        DELETE=all_permissions.projects_delete,
        PATCH=all_permissions.projects_change,
        PUT=all_permissions.projects_change,
        POST=all_permissions.projects_create,
    )
    serializer_class = ProjectSerializer

    redirect_route = 'projects:project-detail'
    redirect_kwarg = 'pk'

    def get_queryset(self):
        serializer = GetFieldsSerializer(data=self.request.query_params)
        serializer.is_valid(raise_exception=True)
        fields = serializer.validated_data.get('include')
        if bool_from_request(self.request.query_params, 'dm_fast', False):
            fields = fields if fields is not None else []

        return (
            Project.objects.with_counts(fields=fields)
            .filter(organization=self.request.user.active_organization)
            .select_related('created_by', 'organization')
        )

    def get(self, request, *args, **kwargs):
        return super(ProjectAPI, self).get(request, *args, **kwargs)

    @api_webhook_for_delete(WebhookAction.PROJECT_DELETED)
    def delete(self, request, *args, **kwargs):
        return super(ProjectAPI, self).delete(request, *args, **kwargs)

    @api_webhook(WebhookAction.PROJECT_UPDATED)
    def patch(self, request, *args, **kwargs):
        project = self.get_object()
        label_config = self.request.data.get('label_config')

        # config changes can break view, so we need to reset them
        if label_config:
            try:
                _has_changes = config_essential_data_has_changed(label_config, project.label_config)
            except KeyError:
                pass

        return super(ProjectAPI, self).patch(request, *args, **kwargs)

    def perform_update(self, serializer):
        instance = serializer.save()
        bump_project_cache_version(instance.id)

    def perform_destroy(self, instance):
        # we don't need to relaculate counters if we delete whole project
        with temporary_disconnect_all_signals():
            instance.delete()

    @extend_schema(exclude=True)
    @api_webhook(WebhookAction.PROJECT_UPDATED)
    def put(self, request, *args, **kwargs):
        return super(ProjectAPI, self).put(request, *args, **kwargs)


class FinalSubmissionCheckAPI(generics.GenericAPIView):
    permission_required = ViewClassPermission(
        GET=all_permissions.projects_view,
    )

    @extend_schema(
        tags=['Projects'],
        summary='Check if final submission exists',
        responses={
            200: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description='Exists flag and record id if present',
            )
        },
    )
    def get(self, request, pk):
        cache_key = _final_submission_check_cache_key(pk, request.user.id)
        cached_payload = cache.get(cache_key)
        if cached_payload is not None:
            return Response(cached_payload)

        upload_payload = cache.get(_final_submission_upload_cache_key(pk, request.user.id)) or {}
        upload_status = upload_payload.get('status')
        if upload_status in FINAL_SUBMISSION_UPLOAD_BLOCKING_STATUSES:
            payload = {
                'exists': True,
                'id': upload_payload.get('final_submission_id'),
                'lunor_submission_id': upload_payload.get('lunor_submission_id'),
                'status': upload_status,
            }
            cache.set(cache_key, payload, FINAL_SUBMISSION_CHECK_CACHE_TIMEOUT)
            return Response(payload)
        if upload_status == 'failed':
            payload = {
                'exists': False,
                'id': None,
                'status': 'failed',
                'error': upload_payload.get('error'),
            }
            cache.set(cache_key, payload, FINAL_SUBMISSION_CHECK_CACHE_TIMEOUT)
            return Response(payload)

        project_scope = Project.objects.filter(pk=pk).values('challenge_id', 'round').first()
        if project_scope is None:
            raise Http404

        challenge_id = _normalize_submission_scope_value(project_scope['challenge_id'])
        round_value = _normalize_submission_scope_value(project_scope['round'])
        submission_id = (
            FinalSubmission.objects.filter(
                project_id=pk,
                user_id=request.user.id,
                challenge_id=challenge_id,
                round=round_value,
            )
            .values_list('id', flat=True)
            .first()
        )
        payload = {
            'exists': submission_id is not None,
            'id': submission_id,
        }
        cache.set(cache_key, payload, FINAL_SUBMISSION_CHECK_CACHE_TIMEOUT)
        return Response(payload)


class FinalSubmissionCreateAPI(generics.GenericAPIView):
    permission_required = ViewClassPermission(
        POST=all_permissions.projects_change,
    )

    @extend_schema(
        tags=['Projects'],
        summary='Create a final submission record',
        request=OpenApiTypes.OBJECT,
        responses={201: OpenApiResponse(description='Created'), 200: OpenApiResponse(description='Already exists')},
    )
    def post(self, request, pk):
        user = request.user
        lunor_user_id = getattr(user, 'lunor_userId', None)
        project_scope = Project.objects.filter(pk=pk).values('challenge_id', 'round').first()
        if project_scope is None:
            raise Http404

        challenge_id = _normalize_submission_scope_value(project_scope['challenge_id'])
        round_value = _normalize_submission_scope_value(project_scope['round'])

        obj, created = FinalSubmission.objects.get_or_create(
            project_id=pk,
            user_id=user.id,
            challenge_id=challenge_id,
            round=round_value,
            defaults={
                'submitted_user_id': user.id,
                'lunor_user_id': lunor_user_id or '',
            },
        )
        new_cache_key = _final_submission_check_cache_key(pk, user.id)
        cache.set(new_cache_key, {'exists': True, 'id': obj.id}, FINAL_SUBMISSION_CHECK_CACHE_TIMEOUT)
        status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response({'id': obj.id, 'created': created}, status=status_code)


class LunorSubmissionAssetsUploadSerializer(serializers.Serializer):
    # Present for compatibility/future use; not sent to GraphQL (frontend doesn't send it).
    lunor_submission_id = serializers.IntegerField(required=False, allow_null=True)
    studio_project_id = serializers.IntegerField()
    # Single numeric user id (same for Studio platform and Label Studio DB lookups)
    studio_user_id = serializers.IntegerField()
    # Lunor/Quest platform user id (GraphQL expects this as userId).
    lunor_userId = serializers.CharField()
    # Caller’s view of whether assets list should be updated; we also enforce server-side checks.
    assets_list_check = serializers.BooleanField(required=False, default=True)


class LunorSubmissionAssetsUploadStatusSerializer(serializers.Serializer):
    studio_project_id = serializers.IntegerField()
    studio_user_id = serializers.IntegerField()


def _run_lunor_submission_assets_upload(
    project_id,
    studio_user_id,
    lunor_user_id,
    lunor_submission_id=None,
    assets_list_check=True,
    hostname=None,
):
    project = Project.objects.get(pk=project_id)
    user = User.objects.get(pk=studio_user_id)
    challenge_id = _normalize_submission_scope_value(project.challenge_id)
    round_value = _normalize_submission_scope_value(project.round)
    graphql_user_id = str(lunor_user_id).strip()

    existing_record = _get_existing_final_submission(project_id, studio_user_id, challenge_id, round_value)
    if existing_record:
        cache.set(
            _final_submission_check_cache_key(project_id, studio_user_id),
            {'exists': True, 'id': existing_record['id']},
            FINAL_SUBMISSION_CHECK_CACHE_TIMEOUT,
        )
        _set_final_submission_stage(
            project_id,
            studio_user_id,
            'completed',
            100,
            'Final submission already exists.',
            success=True,
            final_submission_id=existing_record['id'],
        )
        return

    if not challenge_id:
        _set_final_submission_stage(
            project_id,
            studio_user_id,
            'failed',
            100,
            'Final submission failed before upload started.',
            success=False,
            error='Project has no challenge_id; cannot request upload URL.',
        )
        return

    runtime_graphql = getattr(settings, 'GRAPHQL_ENDPOINT', None)
    graphql_endpoint = _resolve_container_localhost_url(
        runtime_graphql or os.environ.get('GRAPHQL_ENDPOINT') or 'https://prod.100protocol.com/'
    )
    reserved_upload = _get_final_submission_reserved_upload(project_id, studio_user_id)
    submission_filename = reserved_upload.get('filename') or _build_final_submission_filename(project_id, studio_user_id)

    try:
        _set_final_submission_stage(
            project_id,
            studio_user_id,
            'exporting',
            5,
            'Preparing filtered annotation export in the background.',
            lunor_submission_id=reserved_upload.get('upload_info', {}).get('submissionId') or lunor_submission_id,
        )
        with get_temp_dir() as tmp_dir:
            export_json_path = pathlib.Path(tmp_dir) / 'export.json'
            export = _create_final_submission_export_snapshot(
                project,
                user,
                progress_callback=lambda payload: _set_final_submission_upload_status(
                    project_id,
                    studio_user_id,
                    payload['status'],
                    **{key: value for key, value in payload.items() if key != 'status'},
                ),
                export_file_path=export_json_path,
            )

            _set_final_submission_stage(
                project_id,
                studio_user_id,
                'converting',
                70,
                'Converting filtered export to CSV.',
                export_id=export.id,
            )
            converted_format, csv_local_path = _convert_final_submission_export_to_csv(
                export,
                project,
                user,
                hostname,
                input_file_path=export_json_path,
                work_dir=tmp_dir,
                output_filename=submission_filename,
            )

            _set_final_submission_stage(
                project_id,
                studio_user_id,
                'uploading',
                82,
                'Uploading CSV to final submission storage.',
                export_id=export.id,
                converted_format_id=converted_format.id,
            )
            upload_info, upload_url, url_arr, submission_filename = _resolve_final_submission_upload_target(
                project_id,
                studio_user_id,
                lunor_user_id,
                challenge_id,
                round_value,
                reserved_upload=reserved_upload,
            )
            uploaded_filename, upload_info, url_arr = _upload_final_submission_csv_with_retry(
                project_id,
                studio_user_id,
                lunor_user_id,
                challenge_id,
                round_value,
                upload_url,
                converted_format,
                csv_local_path,
                progress_callback=lambda bytes_sent, total_bytes: _set_final_submission_stage(
                    project_id,
                    studio_user_id,
                    'uploading',
                    82 + int((bytes_sent * 13) / max(total_bytes, 1)),
                    f'Uploading CSV to final submission storage ({bytes_sent:,} / {total_bytes:,} bytes).',
                    export_id=export.id,
                    converted_format_id=converted_format.id,
                    progress_current=bytes_sent,
                    progress_total=total_bytes,
                ),
            )

        asset_keys = [item.get('key') for item in url_arr if isinstance(item, dict) and item.get('key')]
        if not asset_keys:
            raise RuntimeError('No asset keys returned from GraphQL urlArr.')

        _set_final_submission_stage(
            project_id,
            studio_user_id,
            'finalizing',
            97,
            'Finalizing submission on Quest platform.',
            export_id=export.id,
            converted_format_id=converted_format.id,
            uploaded_filename=uploaded_filename,
        )
        _update_final_submission_asset_list(
            graphql_endpoint,
            upload_info,
            asset_keys,
            challenge_id,
            round_value,
            graphql_user_id,
        )

        final_submission, _created = FinalSubmission.objects.get_or_create(
            project_id=project_id,
            user_id=studio_user_id,
            challenge_id=challenge_id,
            round=round_value,
            defaults={
                'submitted_user_id': studio_user_id,
                'lunor_user_id': getattr(user, 'lunor_userId', None) or '',
            },
        )
        _mark_final_submission_check_accepted(
            project_id,
            studio_user_id,
            upload_info.get('submissionId') or lunor_submission_id,
            final_submission_id=final_submission.id,
        )
        _clear_final_submission_reserved_upload(project_id, studio_user_id)
        _set_final_submission_stage(
            project_id,
            studio_user_id,
            'completed',
            100,
            'Final submission uploaded successfully.',
            success=True,
            export_id=export.id,
            converted_format_id=converted_format.id,
            uploaded_filename=uploaded_filename,
            asset_keys=asset_keys,
            final_submission_id=final_submission.id,
            lunor_submission_id=upload_info.get('submissionId') or lunor_submission_id,
            assets_list_check=assets_list_check,
        )
    except Exception as exc:
        logger.exception(
            'Final submission upload failed for project_id=%s studio_user_id=%s',
            project_id,
            studio_user_id,
        )
        current_payload = cache.get(_final_submission_upload_cache_key(project_id, studio_user_id)) or {}
        _mark_final_submission_check_failed(project_id, studio_user_id, str(exc))
        _clear_final_submission_reserved_upload(project_id, studio_user_id)
        _set_final_submission_stage(
            project_id,
            studio_user_id,
            'failed',
            current_payload.get('percent', 100),
            current_payload.get('message') or 'Final submission failed.',
            success=False,
            export_id=current_payload.get('export_id'),
            converted_format_id=current_payload.get('converted_format_id'),
            uploaded_filename=current_payload.get('uploaded_filename'),
            progress_current=current_payload.get('progress_current'),
            progress_total=current_payload.get('progress_total'),
            lunor_submission_id=current_payload.get('lunor_submission_id'),
            error=str(exc),
        )


class LunorSubmissionAssetsUploadAPI(APIView):
    """Queue the final submission flow and report cache-backed status."""

    permission_classes = [AllowAny]

    def get(self, request):
        serializer = LunorSubmissionAssetsUploadStatusSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        payload = _get_final_submission_upload_status(data['studio_project_id'], data['studio_user_id'])
        return Response(payload, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = LunorSubmissionAssetsUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        project_id = data['studio_project_id']
        studio_user_id = data['studio_user_id']
        lunor_user_id = data.get('lunor_userId')
        lunor_submission_id = data.get('lunor_submission_id')
        assets_list_check = data.get('assets_list_check', True)

        project = generics.get_object_or_404(Project, pk=project_id)
        generics.get_object_or_404(User, pk=studio_user_id)
        challenge_id = _normalize_submission_scope_value(project.challenge_id)
        round_value = _normalize_submission_scope_value(project.round)

        if not challenge_id:
            return Response(
                {'detail': 'Project has no challenge_id; cannot request upload URL.'},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        eligibility_error = _verify_final_submission_eligibility(project, studio_user_id, lunor_user_id)
        if eligibility_error:
            return Response({'detail': eligibility_error}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        existing_record = _get_existing_final_submission(project_id, studio_user_id, challenge_id, round_value)
        if existing_record:
            return Response(
                {
                    'detail': 'Final submission already exists for this user/project/round.',
                    'final_submission_id': existing_record['id'],
                },
                status=status.HTTP_409_CONFLICT,
            )

        cached_status = _get_final_submission_upload_status(project_id, studio_user_id)
        if cached_status.get('status') in FINAL_SUBMISSION_UPLOAD_BLOCKING_STATUSES:
            response_status = (
                status.HTTP_200_OK if cached_status.get('status') == 'completed' else status.HTTP_202_ACCEPTED
            )
            return Response(cached_status, status=response_status)

        if not redis_connected():
            return Response(
                {'detail': 'Redis worker is required for final submission uploads.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        filename = _build_final_submission_filename(project_id, studio_user_id)
        try:
            upload_info, upload_url, url_arr = _request_final_submission_upload_url(
                _get_final_submission_graphql_endpoint(),
                challenge_id,
                str(lunor_user_id).strip(),
                round_value,
                filename,
            )
        except RuntimeError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        lunor_submission_id_from_quest = upload_info.get('submissionId')
        _set_final_submission_reserved_upload(
            project_id,
            studio_user_id,
            upload_info,
            upload_url,
            url_arr,
            filename,
        )

        accepted_payload = _set_final_submission_stage(
            project_id,
            studio_user_id,
            'accepted',
            10,
            'Final submission accepted. Export and upload continue in the background.',
            success=True,
            lunor_submission_id=lunor_submission_id_from_quest,
            submission_id=lunor_submission_id_from_quest,
            submission_filename=filename,
            requested_by_id=getattr(request.user, 'id', None),
        )
        _mark_final_submission_check_accepted(project_id, studio_user_id, lunor_submission_id_from_quest)

        start_job_async_or_sync(
            _run_lunor_submission_assets_upload,
            project_id,
            studio_user_id,
            lunor_user_id,
            lunor_submission_id=lunor_submission_id_from_quest,
            assets_list_check=assets_list_check,
            hostname=request.build_absolute_uri('/'),
            queue_name='critical',
            job_timeout=60 * 60 * 6,
        )
        return Response(accepted_payload, status=status.HTTP_202_ACCEPTED)

# @method_decorator(
#     name='get',
#     decorator=extend_schema(
#         tags=['Projects'],
#         summary='Get next task to label',
#         description="""
#     Get the next task for labeling. If you enable Machine Learning in
#     your project, the response might include a "predictions"
#     field. It contains a machine learning prediction result for
#     this task.
#     """,
#         responses={200: TaskWithAnnotationsAndPredictionsAndDraftsSerializer()},
#     ),
# )
# leaving this method decorator info in case we put it back in swagger API docs
@extend_schema(exclude=True)
class ProjectNextTaskAPI(generics.RetrieveAPIView):
    permission_required = all_permissions.tasks_view
    serializer_class = TaskWithAnnotationsAndPredictionsAndDraftsSerializer
    queryset = Project.objects.all()

    def get(self, request, *args, **kwargs):
        project = self.get_object()
        dm_queue = filters_ordering_selected_items_exist(request.data)
        prepared_tasks = get_prepared_queryset(request, project)

        # If per-user batch size is configured, restrict the queue to the
        # circular batch assigned to this user.
        assignment = get_or_create_user_assignment(request.user, project)
        assigned_flag = assignment is not None
        if assignment is not None:
            prepared_tasks = prepared_tasks.filter(
                id__in=assignment.tasks.values_list('id', flat=True)
            )

        next_task, queue_info = get_next_task(
            request.user,
            prepared_tasks,
            project,
            dm_queue,
            assigned_flag=assigned_flag,
            label_stream_mode=request.data.get('label_stream_mode'),
        )

        if next_task is None:
            raise NotFound(f'There are no tasks for {request.user}')

        # serialize task
        context = {'request': request, 'project': project, 'resolve_uri': True, 'annotations': False}
        serializer = NextTaskSerializer(next_task, context=context)
        response = serializer.data

        response['queue'] = queue_info
        return Response(response)


@extend_schema(exclude=True)
class LabelStreamHistoryAPI(generics.RetrieveAPIView):
    permission_required = all_permissions.tasks_view
    queryset = Project.objects.all()

    def get(self, request, *args, **kwargs):
        project = self.get_object()

        history = get_label_stream_history(request.user, project)

        return Response(history)


@method_decorator(
    name='post',
    decorator=extend_schema(
        tags=['Projects'],
        summary='Validate label config',
        description='Validate an arbitrary labeling configuration.',
        responses={
            204: OpenApiResponse(description='Validation success'),
            400: OpenApiResponse(description='Validation failed'),
        },
        request=ProjectLabelConfigSerializer,
        extensions={
            'x-fern-audiences': ['internal'],
        },
    ),
)
class LabelConfigValidateAPI(generics.CreateAPIView):
    parser_classes = (JSONParser, FormParser, MultiPartParser)
    permission_classes = (AllowAny,)
    serializer_class = ProjectLabelConfigSerializer

    def post(self, request, *args, **kwargs):
        return super(LabelConfigValidateAPI, self).post(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except RestValidationError as exc:
            context = self.get_exception_handler_context()
            response = exception_handler(exc, context)
            response = self.finalize_response(request, response)
            return response

        return Response(status=status.HTTP_204_NO_CONTENT)


@method_decorator(
    name='post',
    decorator=extend_schema(
        tags=['Projects'],
        operation_id='api_projects_validate_label_config',
        summary='Validate project label config',
        description='Determine whether the label configuration for a specific project is valid.',
        parameters=[
            OpenApiParameter(
                name='id',
                type=OpenApiTypes.INT,
                location='path',
                description='A unique integer value identifying this project.',
            ),
        ],
        request=ProjectLabelConfigSerializer,
        extensions={
            'x-fern-sdk-group-name': 'projects',
            'x-fern-sdk-method-name': 'validate_label_config',
            'x-fern-audiences': ['public'],
        },
    ),
)
class ProjectLabelConfigValidateAPI(generics.RetrieveAPIView):
    """Validate label config"""

    parser_classes = (JSONParser, FormParser, MultiPartParser)
    serializer_class = ProjectLabelConfigSerializer
    permission_required = all_permissions.projects_change
    queryset = Project.objects.all()

    def post(self, request, *args, **kwargs):
        project = self.get_object()
        label_config = self.request.data.get('label_config')
        if not label_config:
            raise RestValidationError('Label config is not set or is empty')

        # check new config includes meaningful changes
        has_changed = config_essential_data_has_changed(label_config, project.label_config)
        project.validate_config(label_config, strict=True)
        return Response({'config_essential_data_has_changed': has_changed}, status=status.HTTP_200_OK)

    @extend_schema(exclude=True)
    def get(self, request, *args, **kwargs):
        return super(ProjectLabelConfigValidateAPI, self).get(request, *args, **kwargs)


class ProjectSummaryAPI(generics.RetrieveAPIView):
    parser_classes = (JSONParser,)
    serializer_class = ProjectSummarySerializer
    permission_required = all_permissions.projects_view
    queryset = ProjectSummary.objects.all()

    @extend_schema(exclude=True)
    def get(self, *args, **kwargs):
        return super(ProjectSummaryAPI, self).get(*args, **kwargs)


class ProjectSummaryResetAPI(GetParentObjectMixin, generics.CreateAPIView):
    """This API is useful when we need to reset project.summary.created_labels and created_labels_drafts
    and recalculate them from scratch. It's hard to correctly follow all changes in annotation region
    labels and these fields aren't calculated properly after some time. Label config changes are not allowed
    when these changes touch any labels from these created_labels* dictionaries.
    """

    parser_classes = (JSONParser,)
    parent_queryset = Project.objects.all()
    permission_required = ViewClassPermission(
        POST=all_permissions.projects_change,
    )

    @extend_schema(exclude=True)
    def post(self, *args, **kwargs):
        project = self.parent_object
        summary = project.summary
        start_job_async_or_sync(
            recalculate_created_annotations_and_labels_from_scratch,
            project,
            summary,
            organization_id=self.request.user.active_organization.id,
        )
        return Response(status=status.HTTP_200_OK)


@method_decorator(
    name='get',
    decorator=extend_schema(
        tags=['Projects'],
        summary='Get project import info',
        description='Return data related to async project import operation',
        parameters=[
            OpenApiParameter(
                name='id',
                type=OpenApiTypes.INT,
                location='path',
                description='A unique integer value identifying this project import.',
            ),
        ],
        extensions={
            'x-fern-sdk-group-name': 'tasks',
            'x-fern-sdk-method-name': 'create_many_status',
            'x-fern-audiences': ['public'],
        },
    ),
)
class ProjectImportAPI(generics.RetrieveAPIView):
    permission_required = all_permissions.projects_change
    permission_classes = api_settings.DEFAULT_PERMISSION_CLASSES + [ProjectImportPermission]
    parser_classes = (JSONParser,)
    serializer_class = ProjectImportSerializer
    queryset = ProjectImport.objects.all()
    lookup_url_kwarg = 'import_pk'


@method_decorator(
    name='get',
    decorator=extend_schema(
        tags=['Projects'],
        summary='Get project reimport info',
        description='Return data related to async project reimport operation',
        parameters=[
            OpenApiParameter(
                name='id',
                type=OpenApiTypes.INT,
                location='path',
                description='A unique integer value identifying this project reimport.',
            ),
        ],
        extensions={
            'x-fern-audiences': ['internal'],
        },
    ),
)
class ProjectReimportAPI(generics.RetrieveAPIView):
    permission_required = all_permissions.projects_change
    permission_classes = api_settings.DEFAULT_PERMISSION_CLASSES + [ProjectImportPermission]
    parser_classes = (JSONParser,)
    serializer_class = ProjectReimportSerializer
    queryset = ProjectReimport.objects.all()
    lookup_url_kwarg = 'reimport_pk'


@method_decorator(
    name='delete',
    decorator=extend_schema(
        tags=['Projects'],
        summary='Delete all tasks',
        description='Delete all tasks from a specific project.',
        parameters=[
            OpenApiParameter(
                name='id',
                type=OpenApiTypes.INT,
                location='path',
                description='A unique integer value identifying this project.',
            ),
        ],
        extensions={
            'x-fern-sdk-group-name': 'tasks',
            'x-fern-sdk-method-name': 'delete_all_tasks',
            'x-fern-audiences': ['public'],
        },
    ),
)
@method_decorator(
    name='get',
    decorator=extend_schema(
        tags=['Projects'],  # TODO: deprecate this endpoint in favor of tasks:tasks-list
        summary='List project tasks',
        description="""
            Retrieve a paginated list of tasks for a specific project. For example, use the following cURL command:
            ```bash
            curl -X GET {}/api/projects/{{id}}/tasks/?page=1&page_size=10 -H 'Authorization: Token abc123'
            ```
        """.format(
            settings.HOSTNAME or 'https://localhost:8080'
        ),
        parameters=[
            OpenApiParameter(
                name='id',
                type=OpenApiTypes.INT,
                location='path',
                description='A unique integer value identifying this project.',
            ),
        ]
        + paginator_help('tasks', 'Projects')['parameters'],
        extensions={
            'x-fern-audiences': ['internal'],  # TODO: deprecate this endpoint in favor of tasks:tasks-list
        },
    ),
)
class ProjectTaskListAPI(GetParentObjectMixin, generics.ListCreateAPIView, generics.DestroyAPIView):
    parser_classes = (JSONParser, FormParser)
    queryset = Task.objects.all()
    parent_queryset = Project.objects.all()
    permission_required = ViewClassPermission(
        GET=all_permissions.tasks_view,
        POST=all_permissions.tasks_change,
        DELETE=all_permissions.tasks_delete,
    )
    serializer_class = TaskSerializer
    redirect_route = 'projects:project-settings'
    redirect_kwarg = 'pk'

    def get_serializer_class(self):
        if self.request.method == 'GET':
            return TaskSimpleSerializer
        else:
            return TaskSerializer

    def filter_queryset(self, queryset):
        project = generics.get_object_or_404(
            Project.objects.for_user(self.request.user),
            pk=self.kwargs.get('pk', 0),
        )

        # If per-user batch size is configured, only show the user's
        # assigned circular batch in the project task list.
        assignment = get_or_create_user_assignment(self.request.user, project)
        if assignment is not None:
            tasks = assignment.tasks.all().order_by('-updated_at')
        else:
            # Fallback to original behaviour: show all project tasks
            tasks = Task.objects.filter(project=project).order_by('-updated_at')

        page = paginator(tasks, self.request)
        if page:
            return page
        else:
            raise Http404

    def delete(self, request, *args, **kwargs):
        project = generics.get_object_or_404(Project.objects.for_user(self.request.user), pk=self.kwargs['pk'])
        task_ids = list(Task.objects.filter(project=project).values('id'))
        Task.delete_tasks_without_signals(Task.objects.filter(project=project))
        logger.info(f'calling reset project_id={project.id} ProjectTaskListAPI.delete()')
        project.summary.reset()
        emit_webhooks_for_instance(request.user.active_organization, None, WebhookAction.TASKS_DELETED, task_ids)
        return Response(status=204)

    def get(self, *args, **kwargs):
        return super(ProjectTaskListAPI, self).get(*args, **kwargs)

    @extend_schema(exclude=True)
    def post(self, *args, **kwargs):
        return super(ProjectTaskListAPI, self).post(*args, **kwargs)

    def get_serializer_context(self):
        context = super(ProjectTaskListAPI, self).get_serializer_context()
        context['project'] = self.parent_object
        return context

    def perform_create(self, serializer):
        project = self.parent_object
        instance = serializer.save(project=project)
        emit_webhooks_for_instance(
            self.request.user.active_organization, project, WebhookAction.TASKS_CREATED, [instance]
        )
        return instance


def read_templates_and_groups():
    annotation_templates_dir = find_dir('annotation_templates')
    configs = []
    for config_file in pathlib.Path(annotation_templates_dir).glob('**/*.yml'):
        config = read_yaml(config_file)

        if settings.VERSION_EDITION != 'Community':
            if config.get('group', '').lower() == 'community contributions':
                continue

        if settings.VERSION_EDITION == 'Community':
            if config.get('type', 'community').lower() != 'community':
                continue

        if config.get('image', '').startswith('/static') and settings.HOSTNAME:
            # if hostname set manually, create full image urls
            config['image'] = settings.HOSTNAME + config['image']
        configs.append(config)
    template_groups_file = find_file(os.path.join('annotation_templates', 'groups.txt'))
    with open(template_groups_file, encoding='utf-8') as f:
        groups = f.read().splitlines()

    if settings.VERSION_EDITION != 'Community':
        groups = [group for group in groups if group.lower() != 'community contributions']

    logger.debug(f'{len(configs)} templates found.')
    return {'templates': configs, 'groups': groups}


@extend_schema(exclude=True)
class TemplateListAPI(generics.ListAPIView):
    parser_classes = (JSONParser, FormParser, MultiPartParser)
    permission_required = all_permissions.projects_view
    # load this once in memory for performance
    templates_and_groups = read_templates_and_groups()

    def list(self, request, *args, **kwargs):
        return Response(self.templates_and_groups)


@extend_schema(exclude=True)
class ProjectSampleTask(generics.RetrieveAPIView):
    parser_classes = (JSONParser,)
    queryset = Project.objects.all()
    permission_required = all_permissions.projects_view
    serializer_class = ProjectSerializer

    def post(self, request, *args, **kwargs):
        label_config = self.request.data.get('label_config')
        include_annotation_and_prediction = self.request.data.get('include_annotation_and_prediction', False)

        if not label_config:
            raise RestValidationError('Label config is not set or is empty')

        project = self.get_object()

        if include_annotation_and_prediction:
            try:
                label_interface = LabelInterface(label_config)
                complete_task = label_interface.generate_complete_sample_task(raise_on_failure=True)
                # set the annotation's user id to the current user instead of -1
                user_id = request.user.id
                for annotation in complete_task['annotations']:
                    annotation['completed_by'] = user_id
                return Response({'sample_task': complete_task}, status=200)
            except Exception as e:
                logger.error(
                    f'Error generating enhanced sample task, falling back to original method: {str(e)}. Label config: {label_config}'
                )
                # Fallback to project.get_sample_task if LabelInterface.generate_complete_sample_task failed
                return Response({'sample_task': project.get_sample_task(label_config)}, status=200)
        else:
            # Use the simple sample task generation method
            return Response({'sample_task': project.get_sample_task(label_config)}, status=200)


@extend_schema(exclude=True)
class ProjectModelVersions(generics.RetrieveAPIView):
    parser_classes = (JSONParser,)
    permission_required = all_permissions.projects_view

    def get_queryset(self):
        return Project.objects.filter(organization=self.request.user.active_organization)

    def get(self, request, *args, **kwargs):
        project = self.get_object()
        serializer = ProjectModelVersionParamsSerializer(data=self.request.query_params)
        serializer.is_valid(raise_exception=True)
        extended = serializer.validated_data.get('extended', False)
        include_live_models = serializer.validated_data.get('include_live_models', False)
        limit = serializer.validated_data.get('limit', None)
        data = project.get_model_versions(with_counters=True, extended=extended, limit=limit)

        if extended:
            serializer_models = None
            serializer = ProjectModelVersionExtendedSerializer(data, many=True)

            if include_live_models:
                ml_models = project.get_ml_backends()
                serializer_models = MLBackendSerializer(ml_models, many=True)

            return Response({'static': serializer.data, 'live': serializer_models and serializer_models.data})
        else:
            return Response(data=data)

    def delete(self, request, *args, **kwargs):
        project = self.get_object()
        model_version = request.data.get('model_version', None)

        if not model_version:
            raise RestValidationError('model_version param is required')

        count = project.delete_predictions(model_version=model_version)

        return Response(data=count)


@method_decorator(
    name='get',
    decorator=extend_schema(
        tags=['Projects'],
        summary='List unique annotators for project',
        description='Return unique users who have submitted annotations in the specified project.',
        responses={
            200: OpenApiResponse(
                description='List of annotator users',
                response=UserSimpleSerializer(many=True),
            )
        },
        extensions={
            'x-fern-sdk-group-name': 'projects',
            'x-fern-sdk-method-name': 'list_unique_annotators',
            'x-fern-audiences': ['public'],
        },
    ),
)
class ProjectAnnotatorsAPI(generics.RetrieveAPIView):
    permission_required = all_permissions.projects_view
    queryset = Project.objects.all()

    def get(self, request, *args, **kwargs):
        project = self.get_object()
        annotator_ids = list(
            Annotation.objects.filter(project=project, completed_by_id__isnull=False)
            .values_list('completed_by_id', flat=True)
            .distinct()
        )
        users = User.objects.filter(id__in=annotator_ids).prefetch_related('om_through').order_by('id')
        data = UserSimpleSerializer(users, many=True, context={'request': request}).data
        return Response(data)
