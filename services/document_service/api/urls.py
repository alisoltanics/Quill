from django.urls import path
from .views import ApplyView, HealthView, metrics_view

urlpatterns = [
    path('apply', ApplyView.as_view(), name='apply'),
    path('health', HealthView.as_view(), name='health'),
    path('metrics', metrics_view, name='metrics'),
]
