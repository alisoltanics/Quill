import os
from pathlib import Path

from opentelemetry import trace
from opentelemetry.instrumentation.django import DjangoInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('DJANGO_SECRET', 'dev-secret')
DEBUG = True
ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'api',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
]

ROOT_URLCONF = 'docservice.urls'

TEMPLATES = []

WSGI_APPLICATION = 'docservice.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# If Postgres env vars are provided, override DATABASES for Postgres
POSTGRES_HOST = os.environ.get('POSTGRES_HOST')
if POSTGRES_HOST:
    DATABASES['default'] = {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('POSTGRES_DB', 'docdb'),
        'USER': os.environ.get('POSTGRES_USER', 'docuser'),
        'PASSWORD': os.environ.get('POSTGRES_PASSWORD', 'docpass'),
        'HOST': POSTGRES_HOST,
        'PORT': os.environ.get('POSTGRES_PORT', '5432'),
    }

STATIC_URL = '/static/'

# Use BigAutoField to silence warnings about default auto field
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

OTEL_ENABLED = os.environ.get('OBSERVABILITY_ENABLED', os.environ.get('OTEL_ENABLED', 'false')).lower() == 'true'
if OTEL_ENABLED:
    service_name = os.environ.get('OTEL_SERVICE_NAME', 'document-service')
    endpoint = os.environ.get('OTEL_EXPORTER_OTLP_ENDPOINT', 'http://jaeger:4318')
    resource = Resource.create({
        'service.name': service_name,
        'service.version': '1.0.0',
    })
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=endpoint.rstrip('/') + '/v1/traces')
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    DjangoInstrumentor().instrument()
