from django.db import models


class Document(models.Model):
    # single document example
    content = models.TextField(default='')

    def __str__(self):
        return f'Document {self.pk}'


class DocumentVersion(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='versions')
    content = models.TextField()
    client_id = models.CharField(max_length=128, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'Version {self.pk} of Document {self.document_id} @ {self.created_at.isoformat()}'
