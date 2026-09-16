"""Request/task-local model ownership; never a process-global current user."""
from contextlib import contextmanager
from contextvars import ContextVar, copy_context
from functools import wraps

_MODEL_OWNER = ContextVar('wangcai_model_owner', default='')


def current_model_owner():
    return _MODEL_OWNER.get()


@contextmanager
def model_owner_scope(owner):
    token = _MODEL_OWNER.set(str(owner or ''))
    try:
        yield
    finally:
        _MODEL_OWNER.reset(token)


def scoped_model_call(resolve_owner):
    def decorate(function):
        @wraps(function)
        def call(*args, **kwargs):
            with model_owner_scope(resolve_owner(*args, **kwargs)):
                return function(*args, **kwargs)
        return call
    return decorate


def bind_model_context(function):
    context = copy_context()
    @wraps(function)
    def call(*args, **kwargs):
        return context.run(function, *args, **kwargs)
    return call


class ModelOwnerMiddleware:
    def __init__(self, app, resolve_owner):
        self.app, self.resolve_owner = app, resolve_owner

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        # Keep the context alive through the full streamed response. Threadpool
        # requests inherit it; explicit detached threads bind their own copy.
        with model_owner_scope(self.resolve_owner(scope)):
            await self.app(scope, receive, send)
