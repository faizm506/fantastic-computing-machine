from django.urls import path
from . import views

urlpatterns = [

    path('', views.dashboard, name='dashboard'),
    
    path('new/', views.new_booking, name='new_booking'),
    path('view/<str:booking_id>/', views.booking_detail, name='booking_detail'),
    path('delete/<str:booking_id>/', views.delete_booking, name='delete_booking'),
    
    path('archive/', views.batch_export_view, name='batch_export'),
    path('archive/zip/', views.export_batch_zip, name='export_zip'),
    path('export/excel/', views.export_bookings_csv, name='export_data'),
    path('company/add/', views.add_company, name='add_company'),

    path('switch-company/', views.switch_company, name='switch_company'),
    path('guide/', views.software_guide, name='software_guide'),

    path('edit/<str:booking_id>/', views.edit_booking, name='edit_booking'),
    
    
    
    ]