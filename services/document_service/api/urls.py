from django.urls import path
from .views import (
    DocumentDetailView,
    DocumentListView,
    DocumentPermissionDetailView,
    DocumentShareView,
    FolderDetailView,
    FolderListView,
    HealthView,
    SharedWithMeView,
    metrics_view,
)

urlpatterns = [
    path('health', HealthView.as_view(), name='health'),
    path('metrics', metrics_view, name='metrics'),
    path('folders', FolderListView.as_view(), name='folder-list'),
    path('folders/<int:pk>', FolderDetailView.as_view(), name='folder-detail'),
    path('documents', DocumentListView.as_view(), name='document-list'),
    path('documents/<int:pk>', DocumentDetailView.as_view(), name='document-detail'),
    path('documents/<int:pk>/share', DocumentShareView.as_view(), name='document-share'),
    path('documents/<int:pk>/permissions', DocumentShareView.as_view(), name='document-permissions'),
    path('documents/<int:pk>/permissions/<str:user_email>', DocumentPermissionDetailView.as_view(), name='document-permission-detail'),
    path('shared-with-me', SharedWithMeView.as_view(), name='shared-with-me'),
]
