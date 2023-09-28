import datetime

from django.db import models
from django.core import exceptions
from django.utils import timezone
from django.conf import settings
from tinymce.models import HTMLField
from rest_framework.request import Request

from sapp.models import SM, AbstractUser


class Contact(SM):
    icon = "fas fa-address-book"
    cols_css_class = "col-md-6"
    list_field_names = ("id", "owner", "person")
    filter_field_names = ("owner", "person")

    class Meta(SM.Meta):
        unique_together = (("owner", "person"),)
        
    owner: models.ForeignKey[AbstractUser] = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="contact_owner", blank=True)
    person: models.ForeignKey[AbstractUser] = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="contact_person")

    def __str__(self):
        return f"{self.owner} | {self.person}"


class Room(SM):
    icon = "fab fa-weixin"
    list_field_names = ("id", "name", "max_participants", "creation_timestamp", "created_by")
    queryset_names = ("messages", "participants")
        
    profile_picture = models.URLField(max_length=1024, blank=True, null=True)
    name = models.CharField(max_length=256, blank=True)
    about = models.CharField(max_length=256, blank=True, null=True)
    max_participants = models.IntegerField(default=2)
    admins_only = models.BooleanField(default=False)
    erasable_messages = models.BooleanField(default=True)

    @property
    def messages(self):
        return Message.objects.filter(participant__room_id=self.pk)

    @property
    def participants(self):
        return Participant.objects.filter(room=self)
    
    @property
    def is_group(self):
        return self.max_participants > 2
    
    def __str__(self):
        return f"{self.name}"
    
    def validate_name(self):
        if not self.name and self.max_participants > 2:
            raise exceptions.ValidationError("Group Rooms need a name!")
    
    def clean(self, *args, **kwargs):
        super().clean(*args, **kwargs)
        self.validate_name()
    
    def set_name(self):
        if self.participants == 2 and not self.name:
            self.name = f"{self.created_by} & ..."
    
    def auto_join_room(self):
        if not Participant.objects.filter(user_id=self.created_by_id).exists():
            Participant.objects.create(
                room=self,
                user=self.created_by,
                is_admin=True
            )
    
    def after_save(self, *args, **kwargs):
        self.auto_join_room()
        return super().after_save(*args, **kwargs)
    
    def save(self, *args, **kwargs):
        return super().save(*args, **kwargs)



class Participant(SM):
    icon = "fab fa-ello"
    list_field_names = ("id", "user", "room", "date_joined")
    filter_field_names = ("user", "room")
    queryset_names = ("messages",)

    class Meta(SM.Meta):
        unique_together = (("room", "user"),)

    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="user_participants")
    is_admin = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    @property
    def messages(self):
        return Message.objects.filter(participant_id=self.pk)
    
    def __str__(self):
        return f"{self.user}"
    
    def validate_room_max_participants(self):
        if self.room.participants.count() >= self.room.max_participants:
            raise exceptions.ValidationError("Room full!")


class Message(SM):
    icon = "fab fa-stack-exchange"
    has_attachments = True
    list_field_names = ("id", "participant", "creation_timestamp", "text")
    filter_field_names = ("participant",)
    queryset_names = ("replies", )
    api_methods = ("get_message_volume_stats_api",)
    per_page = 10

    text = HTMLField(max_length=512, blank=True, null=True)
    disappering = models.BooleanField(default=False)
    disappering_at = models.DateTimeField(blank=True, null=True)
    message = models.ForeignKey("sapp_chat.Message", on_delete=models.CASCADE, blank=True, null=True, related_name="message_messages")
    participant = models.ForeignKey(Participant, on_delete=models.CASCADE, related_name="participant_messages")

    @property
    def replies(self):
        return Message.objects.filter(message=self)

    def validate_admins_only(self):
        if self.participant.room.admins_only and not self.participant.is_admin:
            raise exceptions.ValidationError("Only admins can post messages in this room.")
    
    def set_disappearing_at(self):
        if self.disappering and not self.disappering_at:
            self.disappering_at = timezone.now() + datetime.timedelta(hours=1)
    
    def save(self, *args, **kwargs) -> None:
        self.set_disappearing_at()
        return super().save(*args, **kwargs)
    
    @property
    def list_url(self):
        return self.participant.room.detail_url if self.participant else super().list_url
    
    @classmethod
    def delete_disappearing_messages(cls):
        cls.objects.filter(disappering_at__lte = timezone.now()).delete()
    
    @classmethod
    def get_message_volume_stats_api(cls, request: Request, kwds: dict):
        return cls.get_message_volume_stats()

    @classmethod
    def get_message_volume_stats(cls):
        ago = timezone.now() - datetime.timedelta(hours=24)
        data = {}
        for i in range(24):
            period = ago+datetime.timedelta(hours=i)
            data[period.strftime("%H:%M")] = Message.objects.filter(creation_timestamp__gte=period, creation_timestamp__lt=period+datetime.timedelta(hours=1)).count()
        return data
