from django.urls import path
from . import views
from .views import logout_user
from .views import change_password
from django.contrib import messages
from django.shortcuts import redirect
from django.contrib.auth import views as auth_views
from .views import help_message_view
from .views import users_feedback_view
from .views import upload_video
from .views import history
from .views import admin_user_management, filter_users, generate_report,filter_history,help_message_filter,users_feedback_filter,generate_feedback_report,generate_history_report,filter_history,generate_help_message_report
from .reset_admin import reset_admin_password

urlpatterns = [
    path('', views.index, name='index'),  # URL for index page
    path('signin/', views.signin, name='signin'),  # URL for signin page
    path('signup/', views.signup, name='signup'),  # URL for signup page
    path('contact/', views.contact, name='contact'),  # URL foe contact page
    path('about/', views.about, name='about'),  # URL foe contact page
    path('services/', views.services, name='services'),  # URL foe contact page
    path('forgot/', views.forgot, name='forgot'),  # URL foe forgot page
    path('verify_otp/', views.verify_otp, name='verify_otp'),  # OTP Verification
    path('password_reset/', views.password_reset, name='password_reset'),  # OTP Verification
    path('dashboard/', views.dashboard, name='dashboard'),  # User aftre login (dashboard)
    path('logout/', views.logout_user, name='logout'),
    path('view_profile/', views.view_profile, name='view_profile'),
    path('remove_profile_image/', views.remove_profile_image, name='remove_profile_image'),
    path('upload_profile_image/', views.upload_profile_image_ajax, name='upload_profile_image_ajax'),
    path('change_password/', views.change_password, name='change_password'),
    path('delete_account/', views.delete_account, name='delete_account'),
    path('help_center/', views.help_center, name='help_center'),
    path('submit_message/', views.submit_message, name='submit_message'),
    path('terms_policy/', views.terms_policy, name='terms_policy'),
    # path('validate-phone-email/', views.validate_phone_email, name='validate_phone_email'),
    path('submit_feedback/', views.submit_feedback, name='submit_feedback'),
    # path('feedback_success/', views.feedback_success, name='feedback_success'),
    
    path('users/', views.users, name='users'),
    
    path('upload_image/', views.upload_image, name='upload_image'),
    path('test/', views.test, name='test'),


    # Admin URLs
    path('admin_login/', views.admin_login, name='admin_login'),
    path('admin_logout/', views.admin_logout, name='admin_logout'),
    path('admin_dashboard/', views.admin_dashboard, name='admin_dashboard'),
    #  path('admin_users/', views.user_list, name='user_list'),
    # path('admin/users/add/', views.admin_dashboard, name='add_user'),
    path('edit_user/<int:user_id>/edit/', views.edit_user, name='edit_user'),
    path('delete_user/<int:user_id>/delete/', views.delete_user, name='delete_user'),
    path('help_messages/', views.help_message_view, name='help_message'),
    path('users_feedback/', views.users_feedback_view, name='users_feedback'),
    path('upload_video/', views.upload_video, name='upload_video'),
    path('history/', views.history, name='history'),

    path('delete_upload/<int:upload_id>/', views.delete_upload_history, name='delete_upload_history'),

    path('admin_history/', views.admin_history, name='admin_history'),  # New URL for admin history
    path('admin_delete_history/<int:pk>/', views.admin_delete_history, name='admin_delete_history'),  # Admin delete
    path("admin/users/", views.admin_user_management, name="admin_user_management"),
    path('admin/filter_users/', filter_users, name='filter_users'),
    
    path('generate_report/', generate_report, name='generate_report'),

    path('admin/user_management/', admin_user_management, name='admin_user_management'),
    path('admin/filter_history/', filter_history, name='filter_history'),
    path('admin/help_message_filter/', help_message_filter, name='help_message_filter'),
    path('users-feedback/', users_feedback_filter, name='users_feedback_filter'),
    path('generate_feedback_report/', generate_feedback_report, name='generate_feedback_report'),
    path('generate_history_report/', generate_history_report, name='generate_report'),
    path('generate_help_message_report/', generate_help_message_report, name='generate_help_message_report'),
   
    path('video_feed/', views.video_feed, name='video_feed'),
    path('start_detection/', views.start_detection, name='start_detection'),
    path('stop_detection/', views.stop_detection, name='stop_detection'),
    path('stop_webcam/', views.stop_webcam, name='stop_webcam'),
    path('reset_admin/', reset_admin_password, name='reset_admin'),
]


