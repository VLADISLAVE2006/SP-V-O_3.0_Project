from django.conf import settings
from django.conf.urls.static import static
from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from core import views as V

urlpatterns = [
    path("api/health", V.HealthView.as_view()),
    path("api/schema", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs", SpectacularSwaggerView.as_view(url_name="schema")),
    path("api/auth/register", V.RegisterView.as_view()),
    path("api/auth/login", V.LoginView.as_view()),
    path("api/auth/refresh", V.RefreshView.as_view()),
    path("api/auth/logout", V.LogoutView.as_view()),
    path("api/users/me", V.MeView.as_view()),
    path("api/users/me/avatar", V.AvatarView.as_view()),
    path("api/users/me/password", V.PasswordView.as_view()),
    path("api/users/me/polls", V.MyPollsView.as_view()),
    path("api/users/me/responses", V.MyResponsesView.as_view()),
    path("api/users/me/warnings", V.MyWarningsView.as_view()),
    path("api/users/<int:pk>", V.PublicUserView.as_view()),
    path("api/users/<int:pk>/polls", V.PublicUserPollsView.as_view()),
    path("api/polls", V.PollsView.as_view()),
    path("api/polls/<str:slug>", V.PollView.as_view()),
    path("api/polls/<str:slug>/publish", V.PublishView.as_view()),
    path("api/polls/<str:slug>/close", V.CloseView.as_view()),
    path("api/polls/<str:slug>/vote", V.VoteView.as_view()),
    path("api/polls/<str:slug>/results", V.ResultsView.as_view()),
    path("api/polls/<str:slug>/voters", V.VotersView.as_view()),
    path("api/polls/<str:slug>/export", V.ExportView.as_view()),
    path("api/polls/<str:slug>/comments", V.CommentsView.as_view()),
    path("api/comments/<int:pk>", V.CommentView.as_view()),
    path("api/comments/<int:pk>/like", V.LikeView.as_view()),
    path("api/reports", V.ReportsView.as_view()),
    path("api/moderation/reports", V.ModerationReportsView.as_view()),
    path("api/moderation/reports/<int:pk>", V.ReviewReportView.as_view()),
    path("api/moderation/polls/<str:slug>/delete", V.ModerationDeletePollView.as_view()),
    path("api/moderation/comments/<int:pk>/delete", V.ModerationDeleteCommentView.as_view()),
    path("api/moderation/users/<int:pk>/warnings", V.ModerationWarningsView.as_view()),
    path("api/moderation/warnings/<int:pk>", V.DeleteWarningView.as_view()),
    path("api/admin/users", V.AdminUsersView.as_view()),
    path("api/admin/users/<int:pk>/role", V.AdminRoleView.as_view()),
    path("api/admin/users/<int:pk>/ban", V.AdminBanView.as_view()),
    path("api/admin/users/<int:pk>/unban", V.AdminUnbanView.as_view()),
    path("api/admin/users/<int:pk>/bans", V.AdminBansView.as_view()),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
if settings.DEBUG:
    from django.contrib.staticfiles.urls import staticfiles_urlpatterns

    urlpatterns += staticfiles_urlpatterns()
