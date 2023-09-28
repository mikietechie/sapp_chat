from django.shortcuts import render
from django.core.handlers.wsgi import WSGIRequest


def index_view(request: WSGIRequest):
    return render(request, "sapp_chat/index.html")
