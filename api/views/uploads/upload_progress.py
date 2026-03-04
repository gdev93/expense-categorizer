import asyncio
import json
from django.http import StreamingHttpResponse
from django.views import View

class UploadProgressView(View):
    """View to stream upload progress using Server-Sent Events (SSE)"""

    def get(self, request, *args, **kwargs):
        from api.models import UploadFile

        async def event_stream():
            """Async generator for SSE events"""
            last_progress = -1
            retry_count = 0
            max_retries = 300  # 5 minutes if 1s sleep

            while retry_count < max_retries:
                # Get the latest pending/processing upload
                upload = await UploadFile.objects.filter(
                    user=request.user
                ).filter(
                    status__in=['pending', 'processing']
                ).order_by('-upload_date').afirst()

                if not upload:
                    # Check if there's a recently completed upload
                    recent_upload = await UploadFile.objects.filter(
                        user=request.user
                    ).order_by('-upload_date').afirst()

                    if recent_upload and recent_upload.status == 'completed':
                        yield f"data: {json.dumps({'progress': 100, 'status': 'completed', 'file_id': recent_upload.id})}\n\n"
                    break

                if upload.progress != last_progress:
                    yield f"data: {json.dumps({'progress': upload.progress, 'status': upload.status, 'file_id': upload.id})}\n\n"
                    last_progress = upload.progress
                    retry_count = 0  # Reset retry count when progress is made
                else:
                    retry_count += 1

                await asyncio.sleep(1)

        return StreamingHttpResponse(event_stream(), content_type='text/event-stream')
