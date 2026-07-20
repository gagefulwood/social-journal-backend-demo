from django.core.files.uploadhandler import FileUploadHandler, StopUpload


class CappedMediaUploadHandler(FileUploadHandler):
    """Stop a multipart upload once the request-wide file ceiling is crossed."""

    def __init__(self, request, *, maximum_bytes):
        super().__init__(request)
        self.maximum_bytes = maximum_bytes
        self.received_bytes = 0

    def receive_data_chunk(self, raw_data, start):
        self.received_bytes += len(raw_data)
        if self.received_bytes > self.maximum_bytes:
            self.request._media_upload_limit_exceeded = True
            raise StopUpload(connection_reset=False)
        return raw_data

    def file_complete(self, file_size):
        return None
