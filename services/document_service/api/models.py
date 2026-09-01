from django.db import models


class Folder(models.Model):
    user_id = models.IntegerField(db_index=True)
    name = models.CharField(max_length=255, default='New Folder')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'Folder {self.pk} ({self.name}) — user {self.user_id}'


class Document(models.Model):
    user_id = models.IntegerField(db_index=True)
    folder = models.ForeignKey(
        Folder, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='documents'
    )
    title = models.CharField(max_length=255, default='Untitled')
    content = models.TextField(default='')
    yjs_state = models.TextField(default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f'Document {self.pk} ({self.title}) — user {self.user_id}'


class DocumentVersion(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='versions')
    content = models.TextField()
    yjs_state = models.TextField(blank=True, default='')
    client_id = models.CharField(max_length=128, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'Version {self.pk} of Document {self.document_id} @ {self.created_at.isoformat()}'


class DocumentPermission(models.Model):
    ROLE_OWNER = 'owner'
    ROLE_EDITOR = 'editor'
    ROLE_VIEWER = 'viewer'
    ROLE_CHOICES = [
        (ROLE_OWNER, 'Owner'),
        (ROLE_EDITOR, 'Editor'),
        (ROLE_VIEWER, 'Viewer'),
    ]

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='permissions')
    user_email = models.EmailField(db_index=True)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=ROLE_VIEWER)
    granted_by = models.EmailField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('document', 'user_email')
        ordering = ['-created_at']

    def __str__(self):
        return f'Permission {self.pk}: {self.user_email} -> doc {self.document_id} ({self.role})'
