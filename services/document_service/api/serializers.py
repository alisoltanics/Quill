from rest_framework import serializers

from .models import Document, DocumentPermission, DocumentVersion, Folder


# ─── Folder ──────────────────────────────────────────────────────────────────

class FolderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Folder
        fields = ["id", "name", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class FolderCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Folder
        fields = ["id", "name", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]
        extra_kwargs = {
            "name": {"required": False, "default": "New Folder"},
        }


class FolderDetailSerializer(serializers.ModelSerializer):
    documents = serializers.SerializerMethodField()

    class Meta:
        model = Folder
        fields = ["id", "name", "created_at", "updated_at", "documents"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_documents(self, obj):
        docs = obj.documents.all()
        return DocumentSerializer(docs, many=True).data


# ─── Document ────────────────────────────────────────────────────────────────

class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ["id", "folder_id", "title", "content", "yjs_state", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class DocumentCreateSerializer(serializers.Serializer):
    title = serializers.CharField(required=False, default="Untitled", allow_blank=True)
    folder_id = serializers.IntegerField(required=False, allow_null=True, default=None)


class DocumentUpdateSerializer(serializers.Serializer):
    title = serializers.CharField(required=False, allow_blank=True)
    folder_id = serializers.IntegerField(required=False, allow_null=True)
    content = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False)
    yjs_state = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False)
    yjsState = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False)
    full = serializers.BooleanField(required=False, default=True)
    client_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    clientId = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class DocumentVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentVersion
        fields = ["id", "client_id", "yjs_state", "created_at"]
        read_only_fields = ["id", "client_id", "yjs_state", "created_at"]


class DocumentDetailSerializer(serializers.ModelSerializer):
    versions = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = ["id", "folder_id", "title", "content", "yjs_state", "created_at", "updated_at", "versions"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_versions(self, obj):
        versions = obj.versions.order_by("-created_at")[:20]
        return DocumentVersionSerializer(versions, many=True).data


# ─── DocumentPermission ──────────────────────────────────────────────────────

class DocumentPermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentPermission
        fields = ["id", "user_email", "role", "granted_by", "created_at", "updated_at"]
        read_only_fields = ["id", "granted_by", "created_at", "updated_at"]


class ShareCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(
        choices=DocumentPermission.ROLE_CHOICES,
        default=DocumentPermission.ROLE_VIEWER,
    )

    def validate_email(self, value):
        if not value:
            raise serializers.ValidationError("email is required")
        return value


class PermissionUpdateSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=DocumentPermission.ROLE_CHOICES)


# ─── Shared With Me ──────────────────────────────────────────────────────────

class SharedWithMeSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()
    granted_by = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = ["id", "folder_id", "title", "content", "yjs_state", "created_at", "updated_at", "role", "granted_by"]
        read_only_fields = ["id", "folder_id", "title", "content", "yjs_state", "created_at", "updated_at"]

    def get_role(self, obj):
        return getattr(obj, "_shared_role", None)

    def get_granted_by(self, obj):
        return getattr(obj, "_shared_granted_by", None)
