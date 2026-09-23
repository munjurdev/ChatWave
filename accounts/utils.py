def success_response(message, data=None):
    return {"status": "success", "message": message, "data": data or {}}

def error_response(message):
    return {"status": "error", "message": message}

def get_page_params(request):
    try:
        page = int(request.GET.get("page", 1))
    except ValueError:
        page = 1
    try:
        page_size = int(request.GET.get("page_size", 20))
    except ValueError:
        page_size = 20
    return page, page_size

def paginate_queryset(queryset, page, page_size):
    total = queryset.count()
    total_pages = (total + page_size - 1) // page_size if page_size > 0 else 1
    items = queryset[(page - 1) * page_size:page * page_size]
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "items": items
    }
