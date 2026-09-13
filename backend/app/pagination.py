"""Offset pagination for the list endpoints.

Offset rather than cursor, deliberately: the SPA shows numbered pages over data
that is almost always sorted by a business date, and a cursor would buy accuracy
under concurrent inserts that nobody here would notice. If a list ever grows to
the point where `OFFSET` hurts — tens of thousands of pages deep — this is the
one module that has to change.

Totals and other statistics are aggregated in SQL rather than summed from the
returned rows, because the rows are now only one page of them.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Annotated

from fastapi import Depends, Query
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


@dataclass(slots=True)
class PageParams:
    page: int
    size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size


def page_params(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE, alias="pageSize")] = DEFAULT_PAGE_SIZE,
) -> PageParams:
    return PageParams(page=page, size=page_size)


#: Declare on a handler to accept ?page= and ?pageSize=.
Paging = Annotated[PageParams, Depends(page_params)]


def total_for(db: Session, stmt: Select) -> int:
    """How many rows the query would return, without fetching them.

    The ORDER BY is stripped first: it cannot affect a count, and sorting a
    subquery Postgres is only counting is wasted work.
    """
    return db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0


def slice_of(stmt: Select, params: PageParams) -> Select:
    return stmt.limit(params.size).offset(params.offset)


def page_info(params: PageParams, total: int) -> dict:
    pages = max(1, ceil(total / params.size)) if total else 1
    return {
        "page": params.page,
        "pageSize": params.size,
        "total": total,
        "pages": pages,
        "hasMore": params.page < pages,
    }
