"""Cache helpers for API response caching and project-scoped invalidation."""
import hashlib
import json

from django.core.cache import cache


def _project_version_key(project_id: int) -> str:
    return f'project_cache_version:{project_id}'


def get_project_cache_version(project_id: int) -> int:
    if not project_id:
        return 1
    key = _project_version_key(project_id)
    version = cache.get(key)
    if version is None:
        version = 1
        cache.set(key, version, None)
    return int(version)


def bump_project_cache_version(project_id: int) -> int:
    if not project_id:
        return 1
    key = _project_version_key(project_id)
    try:
        # Works for Redis/memcached backends.
        return cache.incr(key)
    except Exception:
        current = get_project_cache_version(project_id)
        new_value = current + 1
        cache.set(key, new_value, None)
        return new_value


def make_api_cache_key(prefix: str, request, project_id: int = None, extra: dict = None) -> str:
    payload = {
        'path': request.path,
        'method': request.method,
        'user_id': getattr(getattr(request, 'user', None), 'id', None),
        'org_id': getattr(getattr(request, 'user', None), 'active_organization_id', None),
        'query': dict(request.GET.lists()),
        'project_id': project_id,
        'project_cache_version': get_project_cache_version(project_id) if project_id else None,
        'extra': extra or {},
    }
    raw = json.dumps(payload, sort_keys=True, default=str)
    digest = hashlib.sha256(raw.encode('utf-8')).hexdigest()
    return f'{prefix}:{digest}'
