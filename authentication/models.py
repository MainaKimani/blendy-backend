import uuid
from django.db import models
from users.models import CustomUser
from organization.models import Organization

class UserSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    token_hash = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    ip_address = models.GenericIPAddressField()
    user_agent = models.CharField(max_length=255)

    def __str__(self):
        return f'{self.user.email} - {self.created_at}'
