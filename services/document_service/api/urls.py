from django.urls import path
from .views import DocumentDetailView, DocumentListView, FolderDetailView, FolderListView, HealthView, metrics_view

urlpatterns = [
    path('health', HealthView.as_view(), name='health'),
    path('metrics', metrics_view, name='metrics'),
    path('folders', FolderListView.as_view(), name='folder-list'),
    path('folders/<int:pk>', FolderDetailView.as_view(), name='folder-detail'),
    path('documents', DocumentListView.as_view(), name='document-list'),
    path('documents/<int:pk>', DocumentDetailView.as_view(), name='document-detail'),
]
