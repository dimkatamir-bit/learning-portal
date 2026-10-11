from django.urls import path

from . import views

urlpatterns = [
    path("verify/<uuid:certificate_uuid>/", views.verify_certificate, name="certificate_verify"),
    path("course/<int:course_id>/issue/", views.retry_certificate, name="certificate_retry"),
    path("<uuid:certificate_uuid>/download/", views.download_certificate, name="certificate_download"),
]
