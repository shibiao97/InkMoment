from __future__ import annotations

from flask import request, url_for

from auth_server.config import (
    ADMIN_API_LIST_LIMIT_MAX,
    DASHBOARD_PAGE_SIZE_CHOICES,
    DEFAULT_DASHBOARD_PAGE_SIZE,
)


def bounded_int(value, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def bounded_limit(value, default: int = 200, maximum: int = ADMIN_API_LIST_LIMIT_MAX) -> int:
    return bounded_int(value, default, 1, maximum)


def pagination_meta(page_param: str, size_param: str, total: int, endpoint: str = "admin_dashboard") -> dict:
    page_size = bounded_int(
        request.args.get(size_param),
        DEFAULT_DASHBOARD_PAGE_SIZE,
        min(DASHBOARD_PAGE_SIZE_CHOICES),
        max(DASHBOARD_PAGE_SIZE_CHOICES),
    )
    if page_size not in DASHBOARD_PAGE_SIZE_CHOICES:
        page_size = DEFAULT_DASHBOARD_PAGE_SIZE
    total = max(0, int(total or 0))
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = bounded_int(request.args.get(page_param), 1, 1, total_pages)
    offset = (page - 1) * page_size
    start = offset + 1 if total else 0
    end = min(total, offset + page_size) if total else 0

    def page_url(next_page: int) -> str:
        args = request.args.to_dict(flat=True)
        args[page_param] = str(next_page)
        args[size_param] = str(page_size)
        return url_for(endpoint, **args)

    first = max(1, page - 2)
    last = min(total_pages, page + 2)
    return {
        "page": page,
        "page_size": page_size,
        "page_size_choices": DASHBOARD_PAGE_SIZE_CHOICES,
        "total": total,
        "total_pages": total_pages,
        "offset": offset,
        "start": start,
        "end": end,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "prev_url": page_url(max(1, page - 1)),
        "next_url": page_url(min(total_pages, page + 1)),
        "first_url": page_url(1),
        "last_url": page_url(total_pages),
        "page_links": [
            {"page": value, "url": page_url(value), "active": value == page} for value in range(first, last + 1)
        ],
    }
