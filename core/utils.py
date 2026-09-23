from rest_framework.views import exception_handler

# Custom Message
def custom_exception_handler(exc, context):
    """
    Global DRF exception handler.
    Always return only first error message.
    """

    response = exception_handler(exc, context)

    if response is None:
        return response

    data = response.data

    # Case 1: {"detail": "..."}
    if isinstance(data, dict) and "detail" in data:
        message = data["detail"]

    # Case 2: serializer errors {"field": ["error"]}
    elif isinstance(data, dict):
        first_error = list(data.values())[0]

        if isinstance(first_error, list):
            message = first_error[0]
        else:
            message = first_error

    # Case 3: ["error"]
    elif isinstance(data, list):
        message = data[0]

    else:
        message = "Something went wrong."

    response.data = {"message": str(message)}

    return response
