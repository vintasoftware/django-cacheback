import logging

from django.conf import settings
from django.core import signals
from django.core.exceptions import ImproperlyConfigured


try:
    import importlib
except ImportError:
    import django.utils.importlib as importlib

try:
    from .tasks import refresh_cache as celery_refresh_cache
except ImportError:
    celery_refresh_cache = None

try:
    import django_rq
    from .rq_tasks import refresh_cache as rq_refresh_cache
except ImportError as exc:
    django_rq = None
    rq_refresh_cache = None


logger = logging.getLogger('cacheback')


class RemovedInCacheback13Warning(DeprecationWarning):
    pass


def get_cache(backend, **kwargs):
    """
    Compatibilty wrapper for getting Django's cache backend instance

    original source:
    https://github.com/vstoykov/django-imagekit/commit/c26f8a0538778969a64ee471ce99b25a04865a8e
    """
    from django.core import cache
    cache = cache._create_cache(backend, **kwargs)
    # Some caches -- python-memcached in particular -- need to do a cleanup at the
    # end of a request cycle. If not implemented in a particular backend
    # cache.close is a no-op.
    if hasattr(cache, 'close'):
        signals.request_finished.connect(cache.close)
    return cache


def get_job_class(klass_str):
    """
    Return the job class
    """
    mod_name, klass_name = klass_str.rsplit('.', 1)
    try:
        mod = importlib.import_module(mod_name)
    except ImportError as e:
        logger.error("Error importing job module %s: '%s'", mod_name, e)
        return
    try:
        klass = getattr(mod, klass_name)
    except AttributeError:
        logger.error("Module '%s' does not define a '%s' class", mod_name, klass_name)
        return
    return klass


def enqueue_task(kwargs, task_options=None):
    task_queue = getattr(settings, 'CACHEBACK_TASK_QUEUE', 'celery')

    if task_queue == 'rq' and rq_refresh_cache is not None:
        return django_rq.get_queue(**task_options or {}).enqueue(rq_refresh_cache, **kwargs)

    elif task_queue == 'celery' and celery_refresh_cache is not None:
        return celery_refresh_cache.apply_async(kwargs=kwargs, **task_options or {})

    raise ImproperlyConfigured('Unkown task queue configured: {0}'.format(task_queue))
