"""This file and its contents are licensed under the Apache License 2.0. Please see the included NOTICE for copyright information and LICENSE for a copy of the license.
"""
import logging
import hmac
import hashlib
from urllib.parse import quote

from core.feature_flags import flag_set
from core.middleware import enforce_csrf_checks
from core.utils.common import load_func
from django.core import signing
from django.contrib.auth import get_user_model
import jwt
from jwt import PyJWKClient
import secrets
import os
from django.conf import settings
from django.contrib import auth
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render, reverse
from django.utils.http import url_has_allowed_host_and_scheme
from organizations.forms import OrganizationSignupForm
from organizations.models import Organization
from rest_framework.authtoken.models import Token
from users import forms
from users.functions import login, proceed_registration

logger = logging.getLogger()


def _derive_secret_from_lunor_id(lunor_user_id: str) -> str:
    """Derive a stable server-side secret from lunor_userId using HMAC-SHA256.

    The returned value is a hex string which we then feed into Django's
    default password hasher via set_password/create_user (second hashing).
    """
    if not lunor_user_id:
        return ''
    secret = (getattr(settings, 'LUNOR_JWT_SECRET', None) or os.getenv('LUNOR_JWT_SECRET') or '').encode('utf-8')
    mac = hmac.new(secret, str(lunor_user_id).encode('utf-8'), digestmod=hashlib.sha256).digest()
    return mac.hex()

@login_required
def logout(request):
    auth.logout(request)

    if settings.LOGOUT_REDIRECT_URL:
        return redirect(settings.LOGOUT_REDIRECT_URL)

    if settings.HOSTNAME:
        redirect_url = settings.HOSTNAME
        if not redirect_url.endswith('/'):
            redirect_url += '/'
        return redirect(redirect_url)
    return redirect('/')


@enforce_csrf_checks
def user_signup(request):
    """Sign up page"""
    user = request.user
    next_page = request.GET.get('next')
    token = request.GET.get('token')

    # checks if the URL is a safe redirection.
    if not next_page or not url_has_allowed_host_and_scheme(url=next_page, allowed_hosts=request.get_host()):
        if flag_set('fflag_all_feat_dia_1777_ls_homepage_short', user):
            next_page = reverse('main')
        else:
            next_page = reverse('projects:project-index')

    user_form = forms.UserSignupForm()
    organization_form = OrganizationSignupForm()

    if user.is_authenticated:
        return redirect(next_page)

    # make a new user
    if request.method == 'POST':
        organization = Organization.objects.first()
        if settings.DISABLE_SIGNUP_WITHOUT_LINK is True:
            if not (token and organization and token == organization.token):
                raise PermissionDenied()
        else:
            if token and organization and token != organization.token:
                raise PermissionDenied()

        user_form = forms.UserSignupForm(request.POST)
        organization_form = OrganizationSignupForm(request.POST)

        if user_form.is_valid():
            redirect_response = proceed_registration(request, user_form, organization_form, next_page)
            if redirect_response:
                return redirect_response

    if flag_set('fflag_feat_front_lsdv_e_297_increase_oss_to_enterprise_adoption_short'):
        return render(
            request,
            'users/new-ui/user_signup.html',
            {
                'user_form': user_form,
                'organization_form': organization_form,
                'next': quote(next_page),
                'token': token,
                'found_us_options': forms.FOUND_US_OPTIONS,
                'elaborate': forms.FOUND_US_ELABORATE,
            },
        )

    return render(
        request,
        'users/user_signup.html',
        {
            'user_form': user_form,
            'organization_form': organization_form,
            'next': quote(next_page),
            'token': token,
        },
    )


@enforce_csrf_checks
def user_login(request):
    """Login page"""
    user = request.user
    next_page = request.GET.get('next')

    # checks if the URL is a safe redirection.
    if not next_page or not url_has_allowed_host_and_scheme(url=next_page, allowed_hosts=request.get_host()):
        if flag_set('fflag_all_feat_dia_1777_ls_homepage_short', user):
            next_page = reverse('main')
        else:
            next_page = reverse('projects:project-index')

    login_form = load_func(settings.USER_LOGIN_FORM)
    form = login_form()

    if user.is_authenticated:
        return redirect(next_page)

    if request.method == 'POST':
        form = login_form(request.POST)
        if form.is_valid():
            user = form.cleaned_data['user']
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            if form.cleaned_data['persist_session'] is not True:
                # Set the session to expire when the browser is closed
                request.session['keep_me_logged_in'] = False
                request.session.set_expiry(0)

            # user is organization member
            org_pk = Organization.find_by_user(user).pk
            user.active_organization_id = org_pk
            user.save(update_fields=['active_organization'])
            return redirect(next_page)

    if flag_set('fflag_feat_front_lsdv_e_297_increase_oss_to_enterprise_adoption_short'):
        return render(request, 'users/new-ui/user_login.html', {'form': form, 'next': quote(next_page)})

    return render(request, 'users/user_login.html', {'form': form, 'next': quote(next_page)})


@login_required
def user_account(request, sub_path=None):
    """
    Handle user account view and profile updates.

    This view displays the user's profile information and allows them to update
    it. It requires the user to be authenticated and have an active organization
    or an organization_pk in the session.

    Args:
        request (HttpRequest): The request object.
        sub_path (str, optional): A sub-path parameter for potential URL routing.
            Defaults to None.

    Returns:
        HttpResponse: Renders the user account template with user profile form,
            or redirects to 'main' if no active organization is found,
            or redirects back to user-account after successful profile update.

    Notes:
        - Authentication is required (enforced by @login_required decorator)
        - Retrieves the user's API token for display in the template
        - Form validation happens on POST requests
    """
    user = request.user

    if user.active_organization is None and 'organization_pk' not in request.session:
        return redirect(reverse('main'))

    form = forms.UserProfileForm(instance=user)
    token = Token.objects.get(user=user)

    if request.method == 'POST':
        form = forms.UserProfileForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            return redirect(reverse('user-account'))

    return render(
        request,
        'users/user_account.html',
        {'settings': settings, 'user': user, 'user_profile_form': form, 'token': token},
    )


@enforce_csrf_checks
def user_authenticate(request):
    """Unified auth endpoint that accepts a signed token to sign in or sign up a user.

    Expected token payload (signed): { email, lunor_userId? }
    """
    user = request.user
    next_page = request.GET.get('next')

    # checks if the URL is a safe redirection.
    if not next_page or not url_has_allowed_host_and_scheme(url=next_page, allowed_hosts=request.get_host()):
        if flag_set('fflag_all_feat_dia_1777_ls_homepage_short', user):
            next_page = reverse('main')
        else:
            next_page = reverse('projects:project-index')

    if user.is_authenticated:
        return redirect(next_page)

    token = request.GET.get('token')
    debug_steps = []
    debug_steps.append('Page loaded')
    context = {
        'next': quote(next_page),
        'status': 'Authenticating from Lunor…',
        'redirect': next_page,
        'error': None,
        'debug_steps': debug_steps,
        'debug_payload': None,
        'jwt_header': None,
        'using_jwt': False,
        'auth_page': True,
    }

    if not token:
        debug_steps.append('No token in query string')
        context['error'] = 'Please login to Lunor Quest url https://app.lunor.quest and then come try to sumbit'
        context['missing_token'] = True
        return render(request, 'users/new-ui/user_authenticate.html', context)

    # Attempt JWT decode first; fallback to Django-signed token for backward compatibility
    payload = None
    email = None
    lunor_userId = None
    using_jwt = False

    LUNOR_JWT_ENABLED = getattr(settings, 'LUNOR_JWT_ENABLED', os.getenv('LUNOR_JWT_ENABLED', 'true').lower() in ('1','true','yes'))
    if LUNOR_JWT_ENABLED:
        algorithms = getattr(settings, 'LUNOR_JWT_ALGORITHMS', None) or os.getenv('LUNOR_JWT_ALGORITHMS', 'RS256,HS256').split(',')
        issuer = getattr(settings, 'LUNOR_JWT_ISSUER', None) or os.getenv('LUNOR_JWT_ISSUER')
        audience = getattr(settings, 'LUNOR_JWT_AUDIENCE', None) or os.getenv('LUNOR_JWT_AUDIENCE')
        jwks_url = getattr(settings, 'LUNOR_JWKS_URL', None) or os.getenv('LUNOR_JWKS_URL')
        shared_secret = getattr(settings, 'LUNOR_JWT_SECRET', None) or os.getenv('LUNOR_JWT_SECRET')

        try:
            key = None
            if jwks_url:
                debug_steps.append('Attempting JWT verification via JWKS URL')
                jwk_client = PyJWKClient(jwks_url)
                signing_key = jwk_client.get_signing_key_from_jwt(token)
                key = signing_key.key
            elif shared_secret:
                debug_steps.append('Attempting JWT verification via shared secret')
                key = shared_secret
            else:
                # Fallback for HS256 in dev: use Django SECRET_KEY if no explicit key provided
                try:
                    header = jwt.get_unverified_header(token)
                    context['jwt_header'] = header
                    if header.get('alg') == 'HS256':
                        debug_steps.append('Attempting JWT verification via Django SECRET_KEY (dev fallback)')
                        key = settings.SECRET_KEY
                except Exception:
                    key = None

            if key is not None:
                debug_steps.append('Decoding JWT')
                options = {"verify_aud": audience is not None}
                payload = jwt.decode(
                    token,
                    key=key,
                    algorithms=algorithms,
                    audience=audience,
                    issuer=issuer,
                    options=options,
                )
                using_jwt = True
                context['using_jwt'] = True
                # Expose sanitized payload for debug
                sanitized = dict(payload)
                if 'password' in sanitized:
                    sanitized['password'] = '***'
                context['debug_payload'] = sanitized
        except Exception as e:
            debug_steps.append(f'JWT verification error: {e.__class__.__name__}: {e}')
            payload = None

    if payload is None:
        # Try Django signed token
        try:
            debug_steps.append('Attempting Django-signed token verification')
            payload = signing.loads(
                token,
                salt=getattr(settings, 'AUTHENTICATE_TOKEN_SALT', 'ls-auth-token'),
                max_age=int(getattr(settings, 'AUTHENTICATE_TOKEN_MAX_AGE', 300)),
            )
            sanitized = dict(payload)
            if 'password' in sanitized:
                sanitized['password'] = '***'
            context['debug_payload'] = sanitized
        except Exception as e:
            debug_steps.append(f'Django-signed token verification error: {e.__class__.__name__}: {e}')
            context['error'] = 'Unable to verify your request. Please try again.'
            return render(request, 'users/new-ui/user_authenticate.html', context)

    # Extract fields
    email_claim = getattr(settings, 'LUNOR_JWT_EMAIL_CLAIM', None) or os.getenv('LUNOR_JWT_EMAIL_CLAIM', 'email')
    username_claim = getattr(settings, 'LUNOR_JWT_USERNAME_CLAIM', None) or os.getenv('LUNOR_JWT_USERNAME_CLAIM', 'lunor_userId')
    subject_as_email = getattr(settings, 'LUNOR_JWT_SUBJECT_AS_EMAIL', None)
    if subject_as_email is None:
        subject_as_email = os.getenv('LUNOR_JWT_SUBJECT_AS_EMAIL', 'false').lower() in ('1','true','yes')

    email = (payload.get(email_claim) or (payload.get('sub') if subject_as_email else '') or '').lower()
    lunor_userId = payload.get(username_claim) or payload.get('preferred_username') or payload.get('username')

    if not email:
        debug_steps.append('Email missing in token payload')
        context['error'] = 'Email is missing. Please go to your profile and update your email in <a href="https://app.lunor.quest" target="_blank">Lunor Quest</a>.'
        return render(request, 'users/new-ui/user_authenticate.html', context)

    User = get_user_model()
    
    # Check if lunor_userId is already linked to another account
    if lunor_userId:
        existing_user_with_lunor_id = User.objects.filter(lunor_userId=lunor_userId).first()
        if existing_user_with_lunor_id and existing_user_with_lunor_id.email != email:
            # Mask email for privacy: show first 3 chars + ...@
            masked_email = existing_user_with_lunor_id.email[:3] + '...@' + existing_user_with_lunor_id.email.split('@')[1]
            debug_steps.append(f'lunor_userId already linked to account {masked_email}')
            context['error'] = f'This account is already linked to another user ({masked_email}). Please contact support.'
            return render(request, 'users/new-ui/user_authenticate.html', context)

    existing = User.objects.filter(email=email).first()

    if existing:
        debug_steps.append('Existing user found; logging in')
        # For JWT-based auth we trust the token; no password needed
        user = existing
        # If JWT provides lunor_userId, require it to match stored value exactly
        if lunor_userId:
            stored = getattr(user, 'lunor_userId', None)
            if not stored:
                debug_steps.append('lunor userId provided but account has none; blocking auto-link')
                context['error'] = 'This account is not yet linked to Lunor. Please sign in using your original method or contact support to link your Lunor ID.'
                return render(request, 'users/new-ui/user_authenticate.html', context)
            if stored != lunor_userId:
                debug_steps.append('lunor userId mismatch for existing email')
                context['error'] = 'Your account is linked to a different Lunor ID. Please contact support.'
                return render(request, 'users/new-ui/user_authenticate.html', context)
            # Do not change password during login
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        # Ensure organization membership and active organization
        try:
            org_pk = Organization.find_by_user(user).pk
            user.active_organization_id = org_pk
            user.save(update_fields=['active_organization'])
        except Exception:
            # Fallback: add to or create default organization
            if Organization.objects.exists():
                org = Organization.objects.first()
                org.add_user(user)
            else:
                org = Organization.create_organization(created_by=user, title='Label Studio')
            user.active_organization = org
            user.save(update_fields=['active_organization'])
        context['status'] = 'Signed in. Redirecting…'
    else:
        # Create new user and set org membership
        debug_steps.append('User not found; creating account')
        if lunor_userId:
            raw_secret = _derive_secret_from_lunor_id(lunor_userId)
            password_for_creation = raw_secret or secrets.token_urlsafe(20)
        else:
            password_for_creation = secrets.token_urlsafe(20)
        user = User.objects.create_user(email=email, password=password_for_creation, lunor_userId=lunor_userId)
        user.username = email.split('@')[0]
        user.save(update_fields=['username'])

        if Organization.objects.exists():
            org = Organization.objects.first()
            org.add_user(user)
        else:
            org = Organization.create_organization(created_by=user, title='Label Studio')
        user.active_organization = org
        user.save(update_fields=['active_organization'])

        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        context['status'] = 'Account created. Redirecting…'

    return render(request, 'users/new-ui/user_authenticate.html', context)
