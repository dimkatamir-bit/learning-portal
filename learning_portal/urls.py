from django.contrib import admin
from django.urls import include, path

from accounts import views as account_views

admin.site.site_header = "Learning Portal · Управление"
admin.site.site_title = "Learning Portal — администратор"
admin.site.index_title = "Управление платформой"
admin.site.index_template = "admin/portal_index.html"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", account_views.home, name="home"),
    path("register/", account_views.register, name="register"),
    path("login/", account_views.sign_in, name="login"),
    path("logout/", account_views.sign_out, name="logout"),
    path("dashboard/", account_views.dashboard, name="dashboard"),
    path("email/pending/", account_views.email_pending, name="email_pending"),
    path("email/resend/", account_views.resend_verification, name="resend_verification"),
    path("email/confirm/<str:token>/", account_views.confirm_email, name="confirm_email"),
    path("courses/", include("courses.urls")),
    path("exams/", include("exams.urls")),
    path("certificates/", include("certificates.urls")),
]
