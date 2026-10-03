from fastapi.routing import APIRoute

from business_brain.api.dependencies import get_auth_context
from business_brain.main import app


def business_routes():
    for included in app.routes:
        router = getattr(included, "original_router", None)
        context = getattr(included, "include_context", None)
        if router is None or context is None:
            continue
        for route in router.routes:
            if isinstance(route, APIRoute):
                yield f"{context.prefix}{route.path}", route


def test_every_business_api_route_requires_authenticated_context() -> None:
    protected = []
    for path, route in business_routes():
        if path == "/api/v1/health":
            continue
        protected.append(path)
        dependency_calls = {dependency.call for dependency in route.dependant.dependencies}
        assert get_auth_context in dependency_calls, f"{path} lacks authentication"

    assert protected


def test_health_is_the_only_public_business_api_route() -> None:
    public = []
    for path, route in business_routes():
        dependency_calls = {dependency.call for dependency in route.dependant.dependencies}
        if get_auth_context not in dependency_calls:
            public.append(path)
    assert public == ["/api/v1/health"]
