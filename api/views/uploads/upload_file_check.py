from django.http import JsonResponse
from django.views import View
from api.models import UploadFile

class UploadFileCheckView(View):
    """View to check if an upload exists or its status"""

    def get(self, request, *args, **kwargs):
        upload_id = request.GET.get('id')
        if not upload_id:
            return JsonResponse({'status': 'error', 'message': 'Missing ID'}, status=400)

        try:
            upload = UploadFile.objects.get(id=upload_id, user=request.user)
            return JsonResponse({
                'id': upload.id,
                'status': upload.status,
                'progress': upload.progress,
                'file_name': upload.file_name,
                'error_message': upload.error_message
            })
        except UploadFile.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Upload not found'}, status=404)
