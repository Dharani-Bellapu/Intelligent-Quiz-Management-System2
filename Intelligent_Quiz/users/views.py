from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from .forms import UserRegisterForm, UserUpdateForm, ProfileUpdateForm
from .models import Profile

# Home Page
def home_view(request):
    return render(request, 'users/home.html')

# Register User
def register_view(request):
    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        username = request.POST.get('username')

        # Check if username already exists
        if User.objects.filter(username=username).exists():
            messages.error(request, f"The username '{username}' is already taken. Please choose another one.")
            return render(request, 'users/register.html', {'form': form})

        if form.is_valid():
            user = form.save()
            Profile.objects.get_or_create(user=user)
            messages.success(request, f"Account created successfully for {user.username}! 🎉 Please log in.")
            return redirect('home')
        else:
            return render(request, 'users/register.html', {'form': form})
    else:
        form = UserRegisterForm()
    return render(request, 'users/register.html', {'form': form})

# Login
def login_view(request):
    if request.method == "POST":
        username = request.POST.get('username')
        password = request.POST.get('password')
        remember = request.POST.get('remember')
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            # Successful login
            login(request, user)
            
            if not remember:
                request.session.set_expiry(0)
            else:
                request.session.set_expiry(1209600)
            
            messages.success(request, 'Login successful! Welcome back.')
            return redirect('home')
        else:
            # Failed login - display error message
            messages.error(request, 'Invalid username or password.')
            return render(request, "users/login.html")  # Stay on login page with error
    
    return render(request, "users/login.html")

# Logout
def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out successfully.")
    return redirect('home')

# Profile Page (new dashboard-style)
@login_required
def profile_view(request):
    if request.method == 'POST':
        u_form = UserUpdateForm(request.POST, instance=request.user)
        p_form = ProfileUpdateForm(request.POST, request.FILES, instance=request.user.profile)
        if u_form.is_valid() and p_form.is_valid():
            u_form.save()
            p_form.save()
            messages.success(request, '✅ Your profile has been updated successfully!')
            return redirect('profile')
    else:
        u_form = UserUpdateForm(instance=request.user)
        p_form = ProfileUpdateForm(instance=request.user.profile)

    return render(request, 'users/profile.html', {'u_form': u_form, 'p_form': p_form})


def categories_view(request):
    return render(request, 'categories.html')