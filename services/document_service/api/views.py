import json
import os
import time
from django.http import JsonResponse, HttpResponse
from rest_framework.views import APIView
from .models import Document, DocumentVersion
from .metrics import CONTENT_TYPE_LATEST, DOCUMENT_SAVE_COUNT, DOCUMENT_SAVE_ERRORS, REDIS_PUBLISH_COUNT, REQUEST_COUNT, REQUEST_LATENCY, get_metrics_payload
import redis

# Simple /apply endpoint:
# - accepts JSON payload (any shape)
# - merges by appending text sent in `text` field to the stored document
# - saves and returns the full document content
# - publishes the saved content to Redis channel `gateway:events` if REDIS_ADDR set

class HealthView(APIView):
    def get(self, request):
        return JsonResponse({'status': 'ok'})


def metrics_view(request):
    payload = get_metrics_payload()
    return HttpResponse(payload, content_type=CONTENT_TYPE_LATEST)


class ApplyView(APIView):
    def post(self, request):
        started = time.time()
        payload = request.data
        text = None
        client_id = None
        if isinstance(payload, dict):
            text = payload.get('text')
            client_id = payload.get('clientId') or payload.get('client_id')
        if text is None:
            try:
                body = request.body.decode('utf-8')
                text = body
            except Exception:
                text = ''

        doc, _ = Document.objects.get_or_create(pk=1)
        full_save = False
        try:
            if isinstance(payload, dict):
                full_save = bool(payload.get('full') or payload.get('replace'))
        except Exception:
            full_save = False

        try:
            if full_save:
                new_content = str(text)
                doc.content = new_content
            else:
                new_content = (doc.content + '\n' + str(text)) if doc.content else str(text)
                doc.content = new_content
            doc.save()
            DOCUMENT_SAVE_COUNT.labels(mode='full' if full_save else 'append').inc()
        except Exception:
            DOCUMENT_SAVE_ERRORS.inc()
            REQUEST_COUNT.labels(method=request.method, path=request.path, status='500').inc()
            REQUEST_LATENCY.labels(method=request.method, path=request.path).observe(time.time() - started)
            return JsonResponse({'error': 'save failed'}, status=500)

        try:
            DocumentVersion.objects.create(document=doc, content=new_content, client_id=client_id)
        except Exception:
            pass

        redis_addr = os.environ.get('REDIS_ADDR')
        if redis_addr:
            try:
                r = redis.Redis.from_url('redis://' + redis_addr)
                message = json.dumps({'doc_id': doc.pk, 'content': doc.content})
                r.publish('gateway:events', message)
                REDIS_PUBLISH_COUNT.inc()
            except Exception:
                pass

        REQUEST_COUNT.labels(method=request.method, path=request.path, status='200').inc()
        REQUEST_LATENCY.labels(method=request.method, path=request.path).observe(time.time() - started)
        return JsonResponse({'id': doc.pk, 'content': doc.content})

    def get(self, request):
        started = time.time()
        doc, created = Document.objects.get_or_create(pk=1)
        versions = []
        try:
            for v in doc.versions.all().order_by('-created_at')[:20]:
                versions.append({'id': v.pk, 'client_id': v.client_id, 'created_at': v.created_at.isoformat(), 'content': v.content})
        except Exception:
            versions = []
        REQUEST_COUNT.labels(method=request.method, path=request.path, status='200').inc()
        REQUEST_LATENCY.labels(method=request.method, path=request.path).observe(time.time() - started)
        return JsonResponse({'id': doc.pk, 'content': doc.content, 'versions': versions})
