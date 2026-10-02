from uuid import UUID, uuid4

from fastapi import Request


def request_id_from_header(value: str | None) -> str:
    if value:
        try:
            return str(UUID(value))
        except ValueError:
            pass
    return str(uuid4())


def get_request_id(request: Request) -> str:
    return request.state.request_id

