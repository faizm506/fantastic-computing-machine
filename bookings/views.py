import io
import zipfile
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.db.models import Count, Sum, Q
from django.db import transaction
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from weasyprint import HTML
from openpyxl import Workbook
from .models import ActivityLog, Booking, Profile

# --- PUBLIC VIEWS ---

def home(request):
    return render(request, 'home.html')

# --- DASHBOARD & MANAGEMENT ---

from django.core.paginator import Paginator # Add this import
from django.db.models import Q, Sum
@login_required
def dashboard(request):
    try:
        company = request.user.profile.company
    except ObjectDoesNotExist:
        return HttpResponse("Error: Unauthorized Node Access.", status=403)

    # Capture both search and status filter
    query = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status_filter', '').strip()
    
    # 1. Base Filter by Company
    base_bookings = Booking.objects.filter(company=company).order_by('-created_at')

    # 2. Advanced Search & Status Logic
    filtered_bookings = base_bookings

    if query:
        filtered_bookings = filtered_bookings.filter(
            Q(customer_name__icontains=query) | 
            Q(booking_id__icontains=query) |
            Q(receipt_number__icontains=query)
        )
    
    if status_filter:
        filtered_bookings = filtered_bookings.filter(payment_status=status_filter)

    # 3. Pagination
    paginator = Paginator(filtered_bookings, 10)
    page_number = request.GET.get('page')
    bookings_page = paginator.get_page(page_number)

    # 4. Optimized Stats (Re-calculated to include Revenue & Balance)
    # We add Sum of price and Sum of paid to calculate the "Outstanding Balance"
    stats = filtered_bookings.aggregate(
        total_pax=Sum('total_members'),
        total_revenue=Sum('tour_price'),
        total_collected=Sum('amount_paid'),
        total_unpaid=Count('id', filter=~Q(payment_status='Paid'))
    )

    # Calculate Outstanding Balance for the UI
    rev = stats['total_revenue'] or 0
    col = stats['total_collected'] or 0
    remaining_balance = rev - col

    companies = Company.objects.all().order_by('name') if request.user.is_superuser else None
    
    # select_related avoids "N+1" queries when showing usernames in the Pulse feed
    activities = ActivityLog.objects.filter(company=company).select_related('user')[:10]

    context = {
        'bookings': bookings_page,
        'total_travelers': stats['total_pax'] or 0,
        'total_revenue': rev,
        'remaining_balance': remaining_balance,
        'unpaid_count': stats['total_unpaid'] or 0,
        'companies': companies,
        'current_company': company,
        'activities': activities,
        'query': query,
        'status_filter': status_filter,
    }
    
    return render(request, 'bookings/dashboard.html', context)


@login_required
def switch_company(request):
    # Only allow superusers to switch workspaces
    if request.method == 'POST' and request.user.is_superuser:
        company_id = request.POST.get('company_id')
        if company_id:
            new_company = get_object_or_404(Company, id=company_id)
            # Update the Superuser's active profile
            request.user.profile.company = new_company
            request.user.profile.save()
            
    return redirect('dashboard')



@login_required
def new_booking(request):
    if request.method == 'POST':
        # 1. Construct Passenger Manifest
        names = request.POST.getlist('pax_name[]')
        passports = request.POST.getlist('pax_passport[]')
        pans = request.POST.getlist('pax_pan[]')
        dobs = request.POST.getlist('pax_dob[]')
        
        manifest = []
        for i in range(len(names)):
            if names[i].strip():
                manifest.append({
                    "name": names[i],
                    "passport": passports[i] if i < len(passports) else "",
                    "pan": pans[i] if i < len(pans) else "",
                    "dob": dobs[i] if i < len(dobs) else ""
                })

        def get_date(key):
            val = request.POST.get(key)
            return val if val else None

        # --- FIX LOGIC START ---
        # Capture values and handle potential empty strings/whitespace
        payment_stage = request.POST.get('payment_stage', '').strip()
        tour_price = float(request.POST.get('tour_price') or 0)
        amount_paid = float(request.POST.get('amount_paid') or 0)

        # Logic: Mark as Paid if stage is 'Final' (any case) OR if full amount is cleared
        if payment_stage.title() == 'Final' or (amount_paid >= tour_price and tour_price > 0):
            calculated_status = 'Paid'
        else:
            calculated_status = 'Pending'
        # --- FIX LOGIC END ---

        # 2. Atomic Transaction for Booking and Pulse Attribution
        try:
            with transaction.atomic():
                # Create the Booking object
                booking = Booking.objects.create(
                    company=request.user.profile.company,
                    receipt_number=request.POST.get('receipt_number'),
                    booking_date=get_date('booking_date'),
                    cid_number=request.POST.get('cid_number'),
                    customer_name=request.POST.get('customer_name'),
                    contact_mobile=request.POST.get('contact_mobile'),
                    contact_email=request.POST.get('contact_email'),
                    address=request.POST.get('address'),
                    total_members=len(manifest),
                    passenger_manifest=manifest, 
                    tour_price=tour_price,
                    amount_paid=amount_paid,
                    payment_mode=request.POST.get('payment_mode'),
                    cheque_number=request.POST.get('cheque_number'),
                    cheque_date=get_date('cheque_date'),
                    payment_stage=payment_stage,
                    final_payment_due_date=get_date('final_payment_due_date'),
                    payment_status=calculated_status, # Using the fixed logic variable
                    remarks=request.POST.get('remarks')
                )

                # 3. Pulse Attribution
                latest_log = ActivityLog.objects.filter(
                    reference_id=booking.booking_id,
                    company=request.user.profile.company
                ).first()

                if latest_log:
                    latest_log.user = request.user
                    latest_log.save()
            
            return redirect('dashboard')
            
        except Exception as e:
            return render(request, 'bookings/booking_form.html', {'error': str(e)})

    return render(request, 'bookings/booking_form.html')
@login_required
def booking_detail(request, booking_id):
    # 1. Security: Ensure the booking belongs to the user's company
    booking = get_object_or_404(Booking, booking_id=booking_id, company=request.user.profile.company)
    
    # 2. Calculation: Handle balance math in Python to avoid Template Errors
    # We use a simple subtraction; if amount_paid > tour_price, balance becomes 0
    balance_due = max(0, booking.tour_price - booking.amount_paid)

    context = {
        'booking': booking,
        'balance_due': balance_due, # This fixes the 'subtract' filter error
    }
    
    return render(request, 'bookings/booking_detail.html', context)

@login_required
def delete_booking(request, booking_id):
    booking = get_object_or_404(Booking, booking_id=booking_id, company=request.user.profile.company)
    if request.method == 'POST':
        booking.delete()
    return redirect('dashboard')

# --- EXPORT & ARCHIVE CENTER ---

@login_required
def batch_export_view(request):
    company = request.user.profile.company
    start_date = request.GET.get('from_date')
    end_date = request.GET.get('to_date')
    
    bookings = Booking.objects.filter(company=company).order_by('-created_at')
    
    if start_date and end_date:
        bookings = bookings.filter(created_at__date__range=[start_date, end_date])

    # Calculate "Insight Pills" stats
    stats = bookings.aggregate(total_rev=Sum('tour_price'), total_pax=Sum('total_members'))
    
    context = {
        'bookings': bookings,
        'total_revenue': stats['total_rev'] or 0,
        'total_pax': stats['total_pax'] or 0,
        'from_date': start_date,
        'to_date': end_date,
    }
    return render(request, 'bookings/batch_export.html', context)

@login_required
def export_batch_zip(request):
    company = request.user.profile.company
    start_date = request.GET.get('from_date')
    end_date = request.GET.get('to_date')
    
    # 1. VALIDATION: Prevent the "invalid date format" crash
    if not start_date or not end_date:
        return HttpResponse(
            '<script>alert("Please select both start and end dates."); window.history.back();</script>', 
            status=400
        )

    try:
        # 2. DATA RETRIEVAL: Filter by company and date range
        bookings = Booking.objects.filter(
            company=company, 
            created_at__date__range=[start_date, end_date]
        ).order_by('-created_at') # Corrected from .order_at
        
        if not bookings.exists():
             return HttpResponse(
                '<script>alert("No records found for the selected period."); window.history.back();</script>', 
                status=404
            )

        # 3. ZIP GENERATION: Process files in memory
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for b in bookings:
                # Render the voucher HTML
                html_context = {
                    'booking': b,
                    'is_pdf': True,
                    'company_name': company.name
                }
                html_string = render_to_string('bookings/booking_detail.html', html_context)
                
                # Convert HTML to PDF
                pdf_file = io.BytesIO()
                HTML(string=html_string, base_url=request.build_absolute_uri('/')).write_pdf(pdf_file)
                
                # Create a professional filename
                clean_name = "".join(x for x in b.customer_name if x.isalnum() or x==' ').strip().replace(" ", "_")
                filename = f"{b.booking_id}_{clean_name}.pdf"
                
                # Add to ZIP
                zip_file.writestr(filename, pdf_file.getvalue())

        # 4. RESPONSE: Stream the ZIP to the manager
        zip_buffer.seek(0)
        response = HttpResponse(zip_buffer.read(), content_type='application/zip')
        
        # Format filename: e.g., Razak_Sons_Backup_2026-02-19.zip
        download_name = f"{company.name.replace(' ', '_')}_Backup_{start_date}.zip"
        response['Content-Disposition'] = f'attachment; filename="{download_name}"'
        
        return response

    except ValidationError:
        return HttpResponse("Invalid date format provided.", status=400)
    except Exception as e:
        return HttpResponse(f"An error occurred during export: {str(e)}", status=500)

@login_required
def export_bookings_csv(request):
    company = request.user.profile.company
    wb = Workbook()
    ws = wb.active
    ws.title = "Bookings"
    
    # Added new fields to the CSV header
    ws.append(['Receipt #', 'UID', 'Client', 'Mobile', 'Pax', 'Price', 'Paid', 'Stage', 'Date'])

    for b in Booking.objects.filter(company=company).order_by('-created_at'):
        ws.append([
            b.receipt_number,
            b.booking_id, 
            b.customer_name, 
            b.contact_mobile,
            b.total_members, 
            b.tour_price, 
            b.amount_paid,
            b.payment_stage,
            b.created_at.replace(tzinfo=None)
        ])

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="{company.name}_Bookings.xlsx"'
    wb.save(response)
    return response



from django.contrib.auth.models import User
from django.contrib.auth.decorators import user_passes_test
from django.contrib import messages
from .models import Company

# Security Check: Is the user a superuser?
def is_superuser(user):
    return user.is_superuser

@user_passes_test(is_superuser)
def add_company(request):
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # 1. Create the new Company
                new_company = Company.objects.create(
                    name=request.POST.get('company_name'),
                    id_prefix=request.POST.get('id_prefix').upper(),
                    logo=request.FILES.get('logo')
                )
                
                # 2. Create the User
                manager_user = User.objects.create_user(
                    username=request.POST.get('manager_username'),
                    email=request.POST.get('manager_email'),
                    password=request.POST.get('manager_password')
                )
                
                # 3. FORCE UPDATE the profile connection
                # We use update_or_create to overwrite the Signal's default assignment
                Profile.objects.update_or_create(
                    user=manager_user,
                    defaults={'company': new_company}
                )
                
            return redirect('dashboard')
            
        except Exception as e:
            return HttpResponse(f"Error creating company: {str(e)}", status=400)

    return render(request, 'bookings/add_company.html')

def software_guide(request):
    return render(request, 'bookings/guide.html')


from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.db import transaction
from .models import Booking, ActivityLog

@login_required
def edit_booking(request, booking_id):
    # 1. Fetch the existing record (Securely isolated to the company)
    booking = get_object_or_404(Booking, booking_id=booking_id, company=request.user.profile.company)

    if request.method == 'POST':
        # 2. Reconstruct Manifest from POST data
        names = request.POST.getlist('pax_name[]')
        passports = request.POST.getlist('pax_passport[]')
        pans = request.POST.getlist('pax_pan[]')
        dobs = request.POST.getlist('pax_dob[]')
        
        manifest = []
        for i in range(len(names)):
            if names[i].strip():
                manifest.append({
                    "name": names[i],
                    "passport": passports[i] if i < len(passports) else "",
                    "pan": pans[i] if i < len(pans) else "",
                    "dob": dobs[i] if i < len(dobs) else ""
                })

        try:
            with transaction.atomic():
                # 3. Update core fields
                booking.customer_name = request.POST.get('customer_name')
                booking.contact_mobile = request.POST.get('contact_mobile')
                booking.tour_price = float(request.POST.get('tour_price') or 0)
                booking.amount_paid = float(request.POST.get('amount_paid') or 0)
                booking.payment_stage = request.POST.get('payment_stage')
                
                # 4. Update Manifest & Status
                booking.passenger_manifest = manifest
                booking.total_members = len(manifest)
                
                # Auto-status Logic
                if booking.payment_stage.title() == 'Final' or booking.amount_paid >= booking.tour_price:
                    booking.payment_status = 'Paid'
                else:
                    booking.payment_status = 'Pending'
                
                booking.save()
                messages.success(request, f"Registry #{booking.booking_id} has been successfully updated.")

                # 5. Log the Activity
                ActivityLog.objects.create(
                    company=request.user.profile.company,
                    user=request.user,
                    action=f"Updated Registry #{booking.booking_id}",
                    reference_id=booking.booking_id
                )
            
            return redirect('dashboard')
        except Exception as e:
            return render(request, 'bookings/edit_booking.html', {'booking': booking, 'error': str(e)})

    # GET request: Show form with existing data pre-loaded
    return render(request, 'bookings/edit_booking.html', {'booking': booking})