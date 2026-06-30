from django.core.paginator import Paginator


DEFAULT_PAGE_SIZE = 10


def paginate(request, items, *, per_page=DEFAULT_PAGE_SIZE, page_param="page"):
    paginator = Paginator(items, per_page)
    page_obj = paginator.get_page(request.GET.get(page_param) or 1)

    query_params = request.GET.copy()
    query_params.pop(page_param, None)

    return page_obj, {
        "page_obj": page_obj,
        "page_param": page_param,
        "page_querystring": query_params.urlencode(),
        "page_range": list(
            paginator.get_elided_page_range(
                page_obj.number,
                on_each_side=2,
                on_ends=1,
            )
        ),
        "page_ellipsis": paginator.ELLIPSIS,
        "page_size": per_page,
    }
