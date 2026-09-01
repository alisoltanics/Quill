from django.contrib import admin

from .models import Document, DocumentPermission, DocumentVersion, Folder


@admin.register(Folder)
class FolderAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "user_id", "created_at", "updated_at")
    list_filter = ("created_at",)
    search_fields = ("name",)


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "user_id", "folder", "created_at", "updated_at")
    list_filter = ("created_at",)
    search_fields = ("title",)
    raw_id_fields = ("folder",)


@admin.register(DocumentVersion)
class DocumentVersionAdmin(admin.ModelAdmin):
    list_display = ("id", "document", "client_id", "created_at")
    list_filter = ("created_at",)
    raw_id_fields = ("document",)


@admin.register(DocumentPermission)
class DocumentPermissionAdmin(admin.ModelAdmin):
    list_display = ("id", "document", "user_email", "role", "granted_by", "created_at")
    list_filter = ("role", "created_at")
    search_fields = ("user_email",)
    raw_id_fields = ("document",)
