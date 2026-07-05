import hmac
import os
import hashlib
import random
from functools import wraps
import string
import secrets
import urllib.parse
from urllib.parse import urlparse


from flask import Flask, render_template, url_for, abort, request, redirect, jsonify, flash, send_from_directory, current_app, g, make_response
import redis
import time
import logging
from datetime import datetime, timezone, timedelta

from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_caching import Cache
from flask_babel import Babel, _
from flask_babel import lazy_gettext as _l


import requests
import settings
import email_tools
import twilio_sms

import bleach
from email_validator import validate_email, EmailNotValidError


def setup_logger():
    # Configure the logging system
    """Configure root logging handlers and output format for the web app.

    Returns:
        None.
    """
    logging.basicConfig(level=logging.WARNING, handlers=[])  # Do not add the implicit handler
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

    # Create a handler and set the formatter
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    # Add the handler to the root logger
    logging.getLogger().addHandler(handler)


setup_logger()

import db
from mobile_api import mobile_api_bp
app = Flask(__name__)
app.config['SECRET_KEY'] = settings.APP_SEC_KEY
app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=30)  # Example: 30 days
app.config['SESSION_COOKIE_DURATION '] = timedelta(days=5)  # Example: 30 days
app.config['BABEL_DEFAULT_LOCALE'] = 'en'
app.config['LANGUAGES'] = ['en', 'es', 'hi', 'zh']  # Supported languages

app.register_blueprint(mobile_api_bp, url_prefix='/users-api-mobile')


def normalize_language_code(lang_code):
    """Normalize locale tags (e.g. zh-CN, es-419) to a supported app language.

    Args:
        lang_code: Raw locale string from route/cookie/browser headers.

    Returns:
        str: Normalized locale in app.config['LANGUAGES'] or default locale.
    """
    default_lang = app.config['BABEL_DEFAULT_LOCALE']
    supported_langs = app.config['LANGUAGES']

    if not lang_code:
        return default_lang

    normalized = str(lang_code).strip().lower().replace('_', '-')
    if normalized in supported_langs:
        return normalized

    # Map regional/script variants to base language (e.g. zh-CN -> zh).
    base_lang = normalized.split('-', 1)[0]
    if base_lang in supported_langs:
        return base_lang

    return default_lang


def resolve_preferred_language():
    """Resolve language preference using cookie first, then Accept-Language headers.

    Returns:
        str: One of app.config['LANGUAGES'].
    """
    lang_cookie = request.cookies.get('lang', False)
    if lang_cookie:
        return normalize_language_code(lang_cookie)

    # Iterate explicit header preferences to support variants like zh-CN, es-419, hi-IN.
    for browser_lang, _quality in request.accept_languages:
        mapped_lang = normalize_language_code(browser_lang)
        if mapped_lang in app.config['LANGUAGES']:
            return mapped_lang

    # Keep best_match as a final fallback.
    best_match = request.accept_languages.best_match(app.config['LANGUAGES'])
    return normalize_language_code(best_match)


def get_locale():
    # Extract language from the URL 'lang' parameter
    """Resolve the active UI language from route parameters with fallback to default locale.

    Returns:
        str: Active locale code.
    """
    lang = normalize_language_code(request.view_args.get('lang', app.config['BABEL_DEFAULT_LOCALE']))

    logging.warning(f"lang: {lang}")
    return lang


def ensure_language(func):
    """Wrap a view to keep language prefix and cookie preference aligned for GET requests.

    Args:
        func: View function to decorate.

    Returns:
        callable: Wrapped view function.
    """
    def wrapper(*args, **kwargs):
        # Skip language redirect logic for POST requests
        if request.method == "POST":
            return func(*args, **kwargs)
        lang = normalize_language_code(kwargs.get('lang', app.config['BABEL_DEFAULT_LOCALE']))
        preferred_lang = resolve_preferred_language()
        if preferred_lang and preferred_lang != lang:
            query_st = request.query_string.decode()
            if query_st:
                query_st = "?"+query_st
            new_path = request.path + query_st
            if lang != app.config['BABEL_DEFAULT_LOCALE']:
                new_path = new_path.replace(f"/{lang}", "")
            if preferred_lang != app.config['BABEL_DEFAULT_LOCALE']:
                new_path = f"/{preferred_lang}{new_path}"
            logging.warning(f"redirect: {new_path}")
            return redirect(new_path or "/")
        return func(*args, **kwargs)
    wrapper.__name__ = func.__name__  # Required by Flask
    return wrapper


@app.before_request
def before_request():
    # Set `g.lang` so templates can use the active language
    """Initialize per-request language helpers used by templates before view execution.

    Returns:
        None.
    """
    g.img_lang = ''
    if request.view_args:
        g.lang = normalize_language_code(request.view_args.get('lang', app.config['BABEL_DEFAULT_LOCALE']))
        if g.lang != 'en':
            g.img_lang = "_" + g.lang


def get_timezone():
    """Provide timezone information for Flask-Babel from the current request context user.

    Returns:
        str | None: User timezone if available.
    """
    user = getattr(g, 'user', None)
    if user is not None:
        return user.timezone


babel = Babel(app, locale_selector=get_locale, timezone_selector=get_timezone)
app.config.update(settings.WEB_CACHE_SETT)

cache = Cache(app)
db.cache.init_app(app)

RECAPTCHA_SECRET_KEY = settings.APP_RECAPTCHA_SECRET_KEY
RECAPTCHA_PUBLIC_KEY = settings.RECAPTCHA_PUBLIC_KEY

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


login_manager.login_message = _l("Please log in to access this page.")


@login_manager.unauthorized_handler
def unauthorized():
    if request.path.startswith('/users-api-mobile/'):
        return jsonify({"error": "Authentication required"}), 401
    return redirect(url_for('login'))



redis_client = redis.StrictRedis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=settings.WEB_REDIS_DB,
    decode_responses=True
)

DOMAIN = settings.APP_DOMAIN
API_URL = settings.API_DOMAIN
RELEASE_VERSION = "1.0.9"


@app.context_processor
def inject_global_variables():
    """Inject global template variables such as API URL, domain, and support pending flag.

    Returns:
        dict: Values exposed to Jinja templates.
    """
    CONTACT_PENDING = False
    SITE_LOGO_FILE = os.getenv("SITE_LOGO_FILE", "logos/waterlevel.pro.png")

    try:
        cache_key = f'users_support'
        result = redis_client.get(cache_key)
        if result and int(result) > 0:
            CONTACT_PENDING = True
    except Exception as ex:
        logging.exception(ex)
    return {
        'API_URL': API_URL,
        'DOMAIN': DOMAIN,
        'RELEASE_VERSION': RELEASE_VERSION,
        "CONTACT_PENDING": CONTACT_PENDING,
        "SITE_LOGO_FILE": SITE_LOGO_FILE,
        "TRACKING_CONFIG": {
            "enable_tracking": settings.WLP_ENABLE_TRACKING,
            "ga_measurement_id": settings.WLP_GA_MEASUREMENT_ID,
            "twitter_pixel_id": settings.WLP_TWITTER_PIXEL_ID,
            "enable_adsense": settings.WLP_ENABLE_ADSENSE,
            "adsense_client_id": settings.WLP_ADSENSE_CLIENT_ID,
        },
    }


@app.context_processor
def utility_processor():
    """Expose URL helper functions to templates for locale-aware endpoint generation.

    Returns:
        dict: Utility functions for Jinja templates.
    """
    def url_with_lang(endpoint, **kwargs):
        lang = g.get('lang', 'en')
        # Do not add a prefix for the default language
        if lang == app.config['BABEL_DEFAULT_LOCALE']:
            kwargs.pop('lang', None)
            return url_for(endpoint, **kwargs)
        # Add a prefix for non-default languages
        return url_for(endpoint, lang=lang, **kwargs)

    def hreflang_urls():
        """Build hreflang link URLs for all supported languages based on current path.

        Returns:
            dict: Mapping of locale code to full URL for each supported language.
        """
        path = request.path
        clean_path = path
        for code in app.config['LANGUAGES']:
            prefix = f'/{code}'
            if clean_path == prefix:
                clean_path = '/'
                break
            if clean_path.startswith(prefix + '/'):
                clean_path = clean_path[len(prefix):]
                break
        if not clean_path.startswith('/'):
            clean_path = '/' + clean_path

        result = {}
        for code in app.config['LANGUAGES']:
            if code == app.config['BABEL_DEFAULT_LOCALE']:
                result[code] = f"{DOMAIN}{clean_path}"
            else:
                result[code] = f"{DOMAIN}/{code}{clean_path}"
        result['x-default'] = f"{DOMAIN}{clean_path}"
        return result

    return dict(url_with_lang=url_with_lang, hreflang_urls=hreflang_urls)


# Load user callback function required by Flask-Login
@login_manager.user_loader
def load_user(user_id):
    """Load a user record for Flask-Login from the persistent store.

    Args:
        user_id: User identifier from session.

    Returns:
        db.User | None: Authenticated user model or None.
    """
    user_data = db.get_user_by_id(user_id)
    if user_data:
        return db.User(user_data.id, user_data.email, user_data.passw, user_data.is_admin)
    return None


def admin_login_required(func):
    """Restrict access to admin-only views while preserving Flask compatibility behavior.

    Args:
        func: View function requiring admin access.

    Returns:
        callable: Wrapped view function enforcing admin checks.
    """
    @wraps(func)
    def decorated_view(*args, **kwargs):
        print("decorated_view decorated_view decorated_view")
        if request.method in {"OPTIONS"} or current_app.config.get("LOGIN_DISABLED"):
            print("LOGIN DISABLED")
        elif not current_user.is_authenticated or not current_user.is_admin:
            return login_manager.unauthorized()
        else:
            print("LOGIN PASS")

        # flask 1.x compatibility
        # current_app.ensure_sync is only available in Flask >= 2.0
        if callable(getattr(current_app, "ensure_sync", None)):
            return current_app.ensure_sync(func)(*args, **kwargs)
        return func(*args, **kwargs)

    return decorated_view


@app.route('/sensor_stats', methods=['GET'])
def sensor_stats():
    """Return hourly aggregated stats (last 24 hours) for a given sensor public key.

    Query params:
    - public_key: sensor public key or 'demo'

    Returns JSON with 24 hourly buckets (oldest first) containing either
    `percent` and `voltage` (averages) or `offline: true` when no data.
    """
    key = request.args.get('public_key')
    if not key:
        return jsonify({'error': 'missing public_key'}), 400

    if key == 'demo':
        key = settings.DEMO_S1_PUB_KEY

    history_key = f'tin-history/{key}'
    now = int(time.time())
    # Align buckets to hour boundaries and include the current hour
    # Use the next hour boundary as the end so the 24 buckets cover the
    # last 24 one-hour windows including the current hour.
    end = (now - (now % 3600)) + 3600
    start = end - 24 * 3600

    buckets = []
    for i in range(24):
        bucket_start = start + i * 3600
        bucket_end = bucket_start + 3599
        try:
            items = redis_client.zrangebyscore(history_key, bucket_start, bucket_end)
        except Exception:
            items = []

        if not items:
            buckets.append({
                'hour_start': bucket_start,
                'offline': True
            })
            continue

        # parse items "percent|voltage" (legacy) or
        # "percent|voltage|unique_suffix" (current)
        percents = []
        volts = []
        for it in items:
            try:
                parts = it.split('|')
                if len(parts) < 2:
                    continue
                p, v = parts[0], parts[1]
                percents.append(float(p))
                volts.append(float(v))
            except Exception:
                continue

        # Return integer percent values (no decimals) for frontend charts
        avg_percent = int(round(sum(percents) / len(percents))) if percents else None
        avg_voltage = round(sum(volts) / len(volts), 2) if volts else None

        buckets.append({
            'hour_start': bucket_start,
            'offline': False,
            'percent': avg_percent,
            'voltage': avg_voltage
        })

    return jsonify({'buckets': buckets})


@app.route('/sensor_stats_hour', methods=['GET'])
def sensor_stats_hour():
    """Return raw samples for a single hour bucket for a given sensor.

    Query params:
    - public_key: sensor public key or 'demo'
    - hour_start: epoch seconds for the bucket start

    Response: JSON with `samples`: list of { ts, percent, voltage }
    """
    key = request.args.get('public_key')
    hour_start = request.args.get('hour_start')
    if not key or hour_start is None:
        return jsonify({'error': 'missing parameters'}), 400

    try:
        hour_start = int(hour_start)
    except Exception:
        return jsonify({'error': 'invalid hour_start'}), 400

    if key == 'demo':
        key = settings.DEMO_S1_PUB_KEY

    history_key = f'tin-history/{key}'
    bucket_start = hour_start
    bucket_end = bucket_start + 3599

    try:
        items = redis_client.zrangebyscore(history_key, bucket_start, bucket_end, withscores=True)
    except Exception:
        items = []

    samples = []
    for member, score in items:
        try:
            parts = member.split('|')
            if len(parts) < 2:
                continue
            p, v = parts[0], parts[1]
            samples.append({
                'ts': int(score),
                'percent': float(p),
                'voltage': float(v)
            })
        except Exception:
            continue

    # sort by timestamp ascending
    samples.sort(key=lambda x: x['ts'])
    return jsonify({'samples': samples})


@app.route('/relay_consumption_stats', methods=['GET'])
def relay_consumption_stats():
    """Return relay daily stats with estimated costs/energy for a selected period.

    Query params:
    - public_key: relay public key or 'demorelay'
    - month: optional YYYY-MM (defaults to current month)
    - start_date/end_date: optional YYYY-MM-DD custom range (both required)
    """
    key = request.args.get('public_key')
    if not key:
        return jsonify({'error': 'missing public_key'}), 400

    if key == 'demorelay':
        key = settings.DEMO_RELAY_PUB_KEY

    relay_info = db.DevicesDB.load_device_by_public_key(key)
    if not relay_info:
        return jsonify({'error': 'invalid public_key'}), 404
    if int(relay_info.type) != 3:
        return jsonify({'error': 'public_key is not a relay device'}), 400

    today = datetime.now(timezone.utc).date()
    month_param = (request.args.get('month') or '').strip()
    start_date_param = (request.args.get('start_date') or '').strip()
    end_date_param = (request.args.get('end_date') or '').strip()

    range_mode = 'month'
    period_start = None
    period_end = None

    if start_date_param or end_date_param:
        if not start_date_param or not end_date_param:
            return jsonify({'error': 'start_date and end_date are both required'}), 400
        try:
            period_start = datetime.strptime(start_date_param, '%Y-%m-%d').date()
            period_end = datetime.strptime(end_date_param, '%Y-%m-%d').date()
        except Exception:
            return jsonify({'error': 'invalid date format, expected YYYY-MM-DD'}), 400
        if period_end < period_start:
            return jsonify({'error': 'end_date should be >= start_date'}), 400
        if (period_end - period_start).days > 366:
            return jsonify({'error': 'date range too large (max 367 days)'}), 400
        range_mode = 'custom'
    else:
        if month_param:
            try:
                month_dt = datetime.strptime(month_param, '%Y-%m').date()
            except Exception:
                return jsonify({'error': 'invalid month format, expected YYYY-MM'}), 400
            month_start = month_dt.replace(day=1)
        else:
            month_start = today.replace(day=1)
            month_param = month_start.strftime('%Y-%m')

        if month_start.month == 12:
            next_month_start = month_start.replace(year=month_start.year + 1, month=1)
        else:
            next_month_start = month_start.replace(month=month_start.month + 1)
        month_end = next_month_start - timedelta(days=1)

        period_start = month_start
        period_end = today if (month_start.year == today.year and month_start.month == today.month) else month_end

    supported_currency_codes = {
        'USD', 'DOP', 'EUR', 'MXN', 'COP', 'ARS', 'CLP', 'PEN', 'INR', 'CNY'
    }

    relay_settings = db.DevicesDB.load_device_settings(relay_info.id, 3)
    water_cost_per_m3 = float(settings.DEFAULT_WATER_COST_PER_M3)
    relay_power_watts = float(settings.DEFAULT_RELAY_POWER_WATTS)
    energy_cost_per_kwh = float(settings.DEFAULT_ENERGY_COST_PER_KWH)
    currency_code = str(settings.DEFAULT_RELAY_CURRENCY).upper()
    if relay_settings:
        try:
            water_cost_per_m3 = float(relay_settings.get('WATER_COST_PER_M3', water_cost_per_m3) or water_cost_per_m3)
        except Exception:
            water_cost_per_m3 = float(settings.DEFAULT_WATER_COST_PER_M3)
        try:
            relay_power_watts = float(relay_settings.get('RELAY_POWER_WATTS', relay_power_watts) or relay_power_watts)
        except Exception:
            relay_power_watts = float(settings.DEFAULT_RELAY_POWER_WATTS)
        try:
            energy_cost_per_kwh = float(relay_settings.get('ENERGY_COST_PER_KWH', energy_cost_per_kwh) or energy_cost_per_kwh)
        except Exception:
            energy_cost_per_kwh = float(settings.DEFAULT_ENERGY_COST_PER_KWH)
        try:
            currency_candidate = str(relay_settings.get('CURRENCY_CODE', currency_code) or currency_code).strip().upper()
            if currency_candidate in supported_currency_codes:
                currency_code = currency_candidate
        except Exception:
            currency_code = str(settings.DEFAULT_RELAY_CURRENCY).upper()

    if water_cost_per_m3 <= 0:
        water_cost_per_m3 = float(settings.DEFAULT_WATER_COST_PER_M3)
    if relay_power_watts <= 0:
        relay_power_watts = float(settings.DEFAULT_RELAY_POWER_WATTS)
    if energy_cost_per_kwh <= 0:
        energy_cost_per_kwh = float(settings.DEFAULT_ENERGY_COST_PER_KWH)

    days = db.DevicesDB.get_relay_daily_stats(
        relay_info.id,
        start_date=period_start,
        end_date=period_end
    )
    enriched_days = []
    for item in days:
        liters = float(item.get('liters', 0.0) or 0.0)
        on_minutes = int(item.get('on_minutes', 0) or 0)

        water_m3 = liters / 1000.0
        water_cost = water_m3 * water_cost_per_m3

        on_hours = on_minutes / 60.0
        energy_kwh = (relay_power_watts * on_hours) / 1000.0
        energy_cost = energy_kwh * energy_cost_per_kwh
        energy_wh = relay_power_watts * on_hours

        enriched_days.append({
            'day': item.get('day'),
            'on_minutes': on_minutes,
            'liters': round(liters, 2),
            'water_cost': round(water_cost, 4),
            'energy_cost': round(energy_cost, 4),
            'energy_wh': round(energy_wh, 2)
        })

    return jsonify({
        'days': enriched_days,
        'period': {
            'mode': range_mode,
            'start_date': period_start.strftime('%Y-%m-%d'),
            'end_date': period_end.strftime('%Y-%m-%d'),
            'month': month_param if range_mode == 'month' else None,
            'is_current_month': bool(
                range_mode == 'month' and
                period_start.year == today.year and
                period_start.month == today.month
            )
        },
        'settings': {
            'water_cost_per_m3': round(water_cost_per_m3, 4),
            'relay_power_watts': round(relay_power_watts, 2),
            'energy_cost_per_kwh': round(energy_cost_per_kwh, 4),
            'currency_code': currency_code
        }
    })


def validate_recaptcha(response):
    """Verify a reCAPTCHA token against Google verification endpoint.

    Args:
        response: reCAPTCHA token submitted by the client.

    Returns:
        bool: True when verification succeeds.
    """
    data = {
        'secret': RECAPTCHA_SECRET_KEY,
        'response': response
    }
    response = requests.post('https://www.google.com/recaptcha/api/siteverify', data=data)
    result = response.json()
    return result['success']


@app.route('/login', methods=['GET', 'POST'], strict_slashes=False)
@app.route('/<lang>/login', methods=['GET', 'POST'], strict_slashes=False)
@ensure_language
def login(lang='en'):
    """Handle user login flow including form validation and session creation.

    Args:
        lang: Active locale used in localized routes.

    Returns:
        flask.Response: Rendered page or redirect response.
    """
    if request.method == 'POST':
        username = request.form['email']
        password = request.form['password']
        recaptcha_response = request.form['g-recaptcha-response']
        remember = request.form.get('remember') == 'on'

        # Validate reCAPTCHA response
        is_valid_recaptcha = validate_recaptcha(recaptcha_response)

        if not is_valid_recaptcha:
            # Here you can process the form submission, e.g., send an email
            flash(_('Please verify that you are not a robot.'), 'warning')
            return render_template('login.html', RECAPTCHA_PUBLIC_KEY=RECAPTCHA_PUBLIC_KEY)

        password = hashlib.sha256(password.encode()).hexdigest()

        user_data = db.try_login(username, password)
        if user_data and user_data.passw == password:
            if not user_data.confirmed:
                flash(_('Confirm your user email, check inbox or retry register with same email.'), 'warning')
                return render_template('login.html', RECAPTCHA_PUBLIC_KEY=RECAPTCHA_PUBLIC_KEY)
            user = db.User(user_data.id, user_data.email, user_data.passw, user_data.is_admin)
            login_user(user, remember=remember)
            return redirect(url_for('devices'))
        else:
            flash(_('Invalid username or password'), 'warning')
    return render_template('login.html', RECAPTCHA_PUBLIC_KEY=RECAPTCHA_PUBLIC_KEY)


@app.route('/register', methods=['GET', 'POST'], strict_slashes=False)
@app.route('/<lang>/register', methods=['GET', 'POST'], strict_slashes=False)
@ensure_language
def register(lang='en'):
    """Handle user registration flow with validation, anti-spam checks, and confirmation email trigger.

    Args:
        lang: Active locale used in localized routes.

    Returns:
        flask.Response: Rendered page or redirect response.
    """
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        recaptcha_response = request.form['g-recaptcha-response']

        # Validate reCAPTCHA response
        is_valid_recaptcha = validate_recaptcha(recaptcha_response)

        if not is_valid_recaptcha:
            # Here you can process the form submission, e.g., send an email
            flash('Invalid reCAPTCHA response', 'warning')
            return render_template('register.html', RECAPTCHA_PUBLIC_KEY=RECAPTCHA_PUBLIC_KEY)

        try:
            # Validate and normalize the email address
            valid = validate_email(email)
            email = valid.email  # Validated and normalized email
        except EmailNotValidError as e:
            flash('Invalid Email address used.', 'warning')
            return render_template('register.html', RECAPTCHA_PUBLIC_KEY=RECAPTCHA_PUBLIC_KEY)

        if not db.valid_4register(email):
            flash('Email address already in use.', 'warning')
            return render_template('register.html', RECAPTCHA_PUBLIC_KEY=RECAPTCHA_PUBLIC_KEY)

        password = password.encode()
        if not db.add_user(email, hashlib.sha256(password).hexdigest()):
            flash('Fails to add user, contact support.', 'warning')
            return render_template('register.html', RECAPTCHA_PUBLIC_KEY=RECAPTCHA_PUBLIC_KEY)

        email_tools.send_register_email(email, lang=lang)
        flash(_('Register email sent, check inbox.'), 'info')
        return render_template('after_register.html')
    return render_template('register.html', RECAPTCHA_PUBLIC_KEY=RECAPTCHA_PUBLIC_KEY)


@app.route('/user-confirm', methods=['GET'], strict_slashes=False)
@app.route('/<lang>/user-confirm', methods=['GET'], strict_slashes=False)
@ensure_language
def user_confirm(lang='en'):
    """Validate a user confirmation code and activate the account.

    Args:
        lang: Active locale used in localized routes.

    Returns:
        flask.Response: Rendered confirmation page or redirect.
    """
    email = request.args.get('email')
    code = request.args.get('code')
    if email and code:
        if email_tools.check_confirmation_code(email, code):
            db.confirm_user(email)
            flash(_('Confirm success!'), 'success')
        else:
            flash(_('Invalid confirmation code'), 'danger')
    return render_template('user-confirm.html')


@app.route('/settings', methods=['GET', 'POST'], strict_slashes=False)
@app.route('/<lang>/settings', methods=['GET', 'POST'], strict_slashes=False)
@ensure_language
@login_required
def user_settings(lang='en'):
    """Display and update authenticated user settings, alerts, and contact preferences.

    Args:
        lang: Active locale used in localized routes.

    Returns:
        flask.Response: Rendered settings page or redirect.
    """
    if request.method == 'POST':
        action = request.form.get("action")
        if action == 'update-phone':
            phone = request.form.get("phone")
            try:
                phone = int(phone)
                retry_amount = int(redis_client.incr(f"phone/{phone}"))
                redis_client.expire(f"phone/{phone}", 86400)  # 24 hours expire
                if retry_amount > 3:
                    flash('Verify number retry exceeded, wait 24 hours.', 'danger')
                    return redirect(url_for('user_settings'))
                code = random.randint(100000, 900000)
                twilio_sms.send_phone_verify_code(phone, code)
                data = f"{settings.APP_SEC_KEY}-{phone}-{code}"
                auth_hash = hashlib.sha256(data.encode()).hexdigest()
                return render_template('phone_verify.html', auth_hash=auth_hash, phone=phone)
            except Exception as ex:
                logging.exception(ex)
                flash(_('Invalid phone number, use only numbers!'), 'danger')
                return redirect(url_for('user_settings'))
        elif action == 'verify-phone':
            code = request.form.get("code")
            phone = int(request.form.get("phone"))
            auth_hash = request.form.get("auth_hash")
            data = f"{settings.APP_SEC_KEY}-{phone}-{code}"
            auth_hash_check = hashlib.sha256(data.encode()).hexdigest()
            if auth_hash_check == auth_hash:
                current_user.set_phone(phone)
                flash('Phone verify success!', 'success')
                return redirect(url_for('user_settings'))
            else:
                code_retry_amount = int(redis_client.incr(f"phone-code/{phone}"))
                redis_client.expire(f"phone-code/{phone}", 86400)  # 24 hours expire
                if code_retry_amount > 10:
                    flash('Verify code retry exceeded, wait 24 hours!', 'danger')
                    return redirect(url_for('user_settings'))
                flash('Invalid code try again!', 'warning')
                return render_template('phone_verify.html', auth_hash=auth_hash, phone=phone)
        elif action == "update-alert-settings":
            email = request.form.get("email")
            sms = request.form.get("sms")
            frequency = int(request.form.get("frequency"))
            if frequency < 1 or frequency > 48:
                flash(_('Invalid frequency value!'), 'danger')
                return redirect(url_for('user_settings'))
            current_user.set_setting('email-alert', 'on' if email else 'off')
            current_user.set_setting('sms-alert', 'on' if sms else 'off')
            current_user.set_setting('frequency-alert', frequency)

            flash(_('Alert settings update success!'), 'success')
            return redirect(url_for('user_settings'))

    user = db.get_user_by_id(current_user.get_id())
    user_settings = db.User.get_user_settings(current_user.id)
    sms_credits = db.User.get_sms_credits(current_user.id)
    if request.args.get('return', '') == "smscredits":
        flash('Thanks for your purchase, depending on funding sources, it could take some minutes to complete the processing.', 'success')
    if request.args.get('return', '') == "cancel":
        flash('SMS Credits Buy Canceled','warning')
    return render_template('settings.html',
                           user=user, user_settings=user_settings, sms_credits=sms_credits)


@app.route('/index', strict_slashes=False)
@app.route('/', methods=['GET', 'POST'], strict_slashes=False)
@app.route('/<lang>', methods=['GET', 'POST'], strict_slashes=False)
@ensure_language
def index(lang='en'):
    """Render the localized home page.

    Args:
        lang: Active locale used in localized routes.

    Returns:
        flask.Response: Rendered index template.
    """
    return render_template('index.html')


def generate_secure_random_string(length=16):
    """Generate a cryptographically secure random alphanumeric string.

    Args:
        length: Desired number of characters.

    Returns:
        str: Randomly generated token.
    """
    alphabet = string.ascii_letters + string.digits
    password = ''
    while True:
        password = ''.join(secrets.choice(alphabet) for i in range(length))
        if (any(c.islower() for c in password)
                and any(c.isupper() for c in password)
                and sum(c.isdigit() for c in password) >= 3):
            break
    return password


@app.route('/admin_dashboard', methods=['GET', 'POST'], strict_slashes=False)
@login_required
def admin_dashboard():
    """Render the admin dashboard with users and support summary information.

    Returns:
        flask.Response: Rendered admin dashboard page.
    """
    is_admin = current_user.is_admin
    if request.method == 'POST':
        action = request.form.get("action")
        if action == "add-sms-credits" and is_admin:
            user_id = int(request.form.get("user_id"))
            credits = float(request.form.get("credits"))
            db.User.add_sms_credits(user_id, credits)
            flash('Credits added!', category='success')
            return render_template('admin_dashboard.html')
        if action == 'list-sensor' and is_admin:
            return jsonify(db.DevicesDB.get_all_devices_by_type([1, 2]))
        if action == 'list-relay' and is_admin:
            return jsonify(db.DevicesDB.get_all_devices_by_type(3))
        if action == 'list-users' and is_admin:
            return jsonify(db.User.get_all_users())
        if action == 'list-users-support' and is_admin:
            return jsonify(db.Support.get_all_users_support())
        if action in ['add-sensor', 'add-relay']:
            private_key = request.form.get("private_key")
            public_key = request.form.get("public_key")
            dev_name = request.form.get("name", '')

            recaptcha_response = request.form['g-recaptcha-response']

            # Validate reCAPTCHA response
            is_valid_recaptcha = validate_recaptcha(recaptcha_response)

            if not is_valid_recaptcha:
                # Here you can process the form submission, e.g., send an email
                flash('Invalid recaptcha!', category='danger')
                return redirect(url_for('add_sensor' if action == 'add-sensor' else 'add_relay'))

            if not private_key:
                private_key = generate_secure_random_string(22)
            if not public_key:
                public_key = generate_secure_random_string(22)
            note = request.form.get("note", '')
            stype = int(request.form.get("stype", 1))
            device_id = 1 if action == 'add-sensor' else 3
            private_key_format = f"{device_id}prv{private_key}"
            public_key_format = f"{device_id}pub{public_key}"

            if db.DevicesDB.add_device(private_key_format, public_key_format, note, device_id):
                flash(
                    f"Device added <br>public_key: <b>{public_key_format}</b> <br>"
                    f"private_key: <b>{private_key_format}</b>",
                    category='success')
                current_user.add_device(public_key_format, name=dev_name, can_admin=1)
            else:
                flash('Fail to add new device!', category='danger')
                return redirect(url_for('add_sensor'))

            if is_admin:
                return render_template('admin_dashboard.html')
            else:
                return redirect(url_for('user_settings'))
    else:
        if is_admin:
            report_files = os.listdir(settings.REPORTS_FOLDER)
            web_report_files = [fl for fl in report_files if 'api' not in fl.lower()]
            api_report_files = [fl for fl in report_files if 'api' in fl.lower()]
            return render_template('admin_dashboard.html',
                                   web_report_files=web_report_files, api_report_files=api_report_files)
        else:
            return redirect(url_for('login'))


@app.route('/add_sensor', methods=['GET'], strict_slashes=False)
@login_required
def add_sensor():
    """Create a new sensor device record from admin dashboard inputs.

    Returns:
        flask.Response: Redirect response back to admin area.
    """
    is_admin = current_user.is_admin
    return render_template('add_sensor.html',  RECAPTCHA_PUBLIC_KEY=RECAPTCHA_PUBLIC_KEY,
                           is_admin=is_admin)


@app.route('/add_relay', methods=['GET'], strict_slashes=False)
@login_required
def add_relay():
    """Create a new relay device record from admin dashboard inputs.

    Returns:
        flask.Response: Redirect response back to admin area.
    """
    return render_template('add_relay.html',  RECAPTCHA_PUBLIC_KEY=RECAPTCHA_PUBLIC_KEY)


def validate_recaptcha(response):
    """Verify a reCAPTCHA token against Google verification endpoint.

    Args:
        response: reCAPTCHA token submitted by the client.

    Returns:
        bool: True when verification succeeds.
    """
    data = {
        'secret': RECAPTCHA_SECRET_KEY,
        'response': response
    }
    response = requests.post('https://www.google.com/recaptcha/api/siteverify', data=data)
    result = response.json()
    return result['success']


@app.route('/logout', strict_slashes=False)
@app.route('/<lang>/logout', methods=['GET', 'POST'], strict_slashes=False)
@ensure_language
@login_required
def logout(lang='en'):
    """Terminate current user session and redirect to localized login page.

    Args:
        lang: Active locale used in localized routes.

    Returns:
        flask.Response: Redirect response.
    """
    logout_user()
    return redirect(url_for('index'))


def get_relay_event_text(event_code):
    """Convert relay event code to a localized human-readable label.

    Args:
        event_code: Numeric relay event code.

    Returns:
        str: Localized event description.
    """
    RELAY_EVENTS_CODE = {
        0: ("NO_EVENT", _("No event reported")),
        1: ("BLIND_AREA", _("Sensor reach near the blind area!")),
        2: ("BLIND_AREA_DANGER", _("Sensor reach near the danger blind area!")),
        3: ("NOT_FLOW", _("No water inflow detected!")),
        4: ("OFFLINE", _("Offline long time detected!")),
        5: ("IDDLE_SENSOR", _("Offline sensor detected!")),
        6: ("END_LEVEL_EVENT", _("Reach End Level percent!")),
        7: ("START_LEVEL_EVENT", _("Reach Start Level percent!")),
        8: ("SETUP_WIFI", _("Wifi setup started")),
        9: ("BOOT", _("Device boot!")),
        10: ("PUMP_ON", _("Pump ON")),
        11: ("PUMP_OFF", _("Pump OFF")),
        12: ("DATA_POST_FAIL", _("Fail to post data check internet connection")),
        13: ("BTN_PRESS", _("WiFi Reset button pressed")),
        14: ("SENSOR_FAULT", _("Sensor fault or cable disconnected!"))
    }
    return RELAY_EVENTS_CODE[event_code][1]


def format_hours(hours):
    """Format uptime hours into a human-readable days/hours string.

    Args:
        hours: Total uptime in hours.

    Returns:
        str: Formatted uptime text.
    """
    days = hours // 24
    remaining_hours = hours % 24

    parts = []
    if days > 0:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if remaining_hours > 0 or days == 0:
        parts.append(f"{remaining_hours} hour{'s' if remaining_hours != 1 else ''}")

    return ' and '.join(parts)


def _default_relay_device_setting(sensor_key=''):
    """Build a relay settings object suitable for template rendering.

    Args:
        sensor_key: Linked sensor public key shown in the UI.

    Returns:
        db.AttrDict: Relay settings populated with safe defaults.
    """
    return db.AttrDict({
        'ALGO': 0,
        'START_LEVEL': 30,
        'END_LEVEL': 95,
        'AUTO_OFF': 1,
        'AUTO_ON': 1,
        'MIN_FLOW_MM_X_MIN': 10,
        'SENSOR_KEY': sensor_key,
        'BLIND_DISTANCE': 22,
        'HOURS_OFF': '',
        'SAFE_MODE': 1,
        'WATER_COST_PER_M3': float(settings.DEFAULT_WATER_COST_PER_M3),
        'RELAY_POWER_WATTS': float(settings.DEFAULT_RELAY_POWER_WATTS),
        'ENERGY_COST_PER_KWH': float(settings.DEFAULT_ENERGY_COST_PER_KWH),
        'CURRENCY_CODE': settings.DEFAULT_RELAY_CURRENCY,
    })


def _normalize_relay_device_setting(device_setting, sensor_key=''):
    """Coerce relay settings into an AttrDict and backfill template defaults.

    Args:
        device_setting: DB row, mapping-like object, or None.
        sensor_key: Optional linked sensor public key override.

    Returns:
        db.AttrDict: Normalized relay settings for the template.
    """
    normalized = _default_relay_device_setting(sensor_key=sensor_key)

    if device_setting is None:
        return normalized

    if isinstance(device_setting, dict):
        normalized.update(device_setting)
        return normalized

    mapping = getattr(device_setting, '_mapping', None)
    if mapping is not None:
        normalized.update(dict(mapping))
        return normalized

    try:
        normalized.update(dict(device_setting))
    except Exception:
        try:
            normalized.update(vars(device_setting))
        except Exception:
            return normalized
    return normalized


@app.route('/device_info', methods=['GET'], strict_slashes=False)
@app.route('/<lang>/device_info', methods=['GET', 'POST'], strict_slashes=False)
@ensure_language
def device_info(lang='en'):
    """Show device details and telemetry for a selected user device.

    Args:
        lang: Active locale used in localized routes.

    Returns:
        flask.Response: Rendered device details page.
    """
    public_key = request.args.get('public_key')
    private_key = request.args.get('private_key')
    small_version = request.args.get('smallversion')
    return_reason = request.args.get('return')
    can_admin = False
    is_demo = False
    device_alerts = []
    if public_key == "demo":
        public_key = settings.DEMO_S1_PUB_KEY
        is_demo = True
    if public_key == "demorelay":
        public_key = settings.DEMO_RELAY_PUB_KEY
        is_demo = True

    if private_key:
        public_key = db.DevicesDB.valid_private_key(private_key)
        if current_user.is_authenticated and not current_user.can_admin_device(public_key):
            current_user.add_device(public_key, name='', can_admin=1)
            flash(_("Private Key link to your account success! <br> You can now admin device settings."), category='success')
            return redirect(url_for('device_info') + '?public_key=' + public_key)
        if not public_key:
            return render_template('invalid_device.html', key_used=private_key)

    device_info = db.DevicesDB.load_device_by_public_key(public_key)
    if not device_info:
        return render_template('invalid_device.html', key_used=public_key)

    if device_info and current_user.is_authenticated and current_user.can_admin_device(public_key):
        can_admin = True

    working_hours = db.DevicesDB.get_device_uptime(device_info.id)
    working_hours_nice = format_hours(working_hours)

    device_setting = None
    model_info = db.DevicesDB.load_model_info_by_public_key(public_key)
    device_setting = db.DevicesDB.load_device_settings(device_info.id, device_info.type)
    template_name = 'sensor_device_info.html'
    DISPLAY_EVENTS = []
    if device_info.type == 3:
        template_name = 'relay_device_info.html'
        device_setting = _normalize_relay_device_setting(device_setting)
        PAST_EVENTS = db.DevicesDB.get_relay_events(device_info.id)
        if PAST_EVENTS:
            for event in PAST_EVENTS:
                current_event = f"<b>{event['created_at']} GMT-4</b>: "
                for event_code in event['events'].split(","):
                    event_code = int(event_code)
                    if event_code != 0:
                        current_event = current_event + f"<span class='badge text-bg-info fw-bold mx-2 my-2'>{get_relay_event_text(event_code)}</span>"
                DISPLAY_EVENTS.append(current_event)

    if is_demo:
        public_key = 'demo'
        if device_info.type == 3:
            public_key = 'demorelay'
            device_setting = _normalize_relay_device_setting(device_setting, sensor_key='demo')
            device_setting['SENSOR_KEY'] = 'demo'

    active_subs = []
    is_unlocked = True
    buy_options = []
    disabled_device = False

    if current_user.is_authenticated:
        device_alerts = db.User.load_device_alerts(current_user.id, public_key)
    return render_template(template_name, can_admin=can_admin, small_version=small_version, is_unlocked=is_unlocked,
                           device_info=device_info, key_used=public_key, device_alerts=device_alerts,
                           device_setting=device_setting, model_info=model_info, active_subs=active_subs,
                           buy_options=buy_options,
                           disabled_device=disabled_device, return_reason=return_reason, DISPLAY_EVENTS=DISPLAY_EVENTS,
                           working_hours=working_hours, working_hours_nice=working_hours_nice)


@app.route('/device_admin', methods=['POST'])
def device_admin():
    """Handle device administration actions such as update, delete, and ownership settings.

    Returns:
        flask.Response: Redirect response after admin operation.
    """
    action = request.form.get("action")
    is_admin = current_user.is_admin
    public_key = request.form.get("public_key")

    auth = False
    if is_admin or (public_key and current_user.is_authenticated and current_user.can_admin_device(public_key)):
        auth = True

    if not current_user.is_authenticated and action == 'add-alert':
        flash("Login to add alerts!", category='danger')
        return redirect(url_for('device_info') + '?public_key=' + public_key)

    if current_user.is_authenticated and action == 'add-alert':
        condition = int(request.form.get("condition"))
        level = int(request.form.get("level"))
        current_user.add_alert(public_key, condition, level)
        flash("Alert Added!", category='warning')
        return redirect(url_for('device_info') + '?public_key=' + public_key)

    if current_user.is_authenticated and action == 'del-alert':
        condition = int(request.form.get("condition"))
        level = int(request.form.get("level"))
        current_user.delete_alert(public_key, condition, level)
        flash("Alert Removed!", category='warning')
        return redirect(url_for('device_info') + '?public_key=' + public_key)

    if is_admin and action == 'cache-clear':
        redis_client.flushall()
        cache.clear()
        flash("REDIS CACHE FLUSH SENT", category='danger')
        return redirect(url_for('admin_dashboard'))

    if is_admin and action == 'read-support':
        cache_key = f'users_support'
        redis_client.delete(cache_key)
        flash("USER SUPPORT READ SENT", category='danger')
        return redirect(url_for('admin_dashboard'))

    if is_admin and action == 'admin-support':
        email = request.form.get("email")
        message = request.form.get("message")
        flash("Support Email Sent!", category='danger')
        db.Support.add_user_support_record(user_email=email, message=message, support_type=1)
        email_tools.support_email(email, message)
        cache_key = f'users_support'
        result = redis_client.delete(cache_key)
        return redirect(url_for('admin_dashboard'))

    if action == 'relay-setting' and auth:
        if public_key:
            supported_currency_codes = {
                'USD', 'DOP', 'EUR', 'MXN', 'COP', 'ARS', 'CLP', 'PEN', 'INR', 'CNY'
            }
            device = db.DevicesDB.load_device_by_public_key(public_key)
            if device and device.id:
                device_id = device.id
                ALGO = int(1 if request.form.get("ALGO", False) else 0)
                SAFE_MODE = int(1 if request.form.get("SAFE_MODE", False) else 0)
                START_LEVEL = int(request.form.get("START_LEVEL"))
                END_LEVEL = int(request.form.get("END_LEVEL"))
                AUTO_OFF = int(1 if request.form.get("AUTO_OFF", False) else 0)
                AUTO_ON = int(1 if request.form.get("AUTO_ON", False) else 0)
                MIN_FLOW_MM_X_MIN = int(request.form.get("MIN_FLOW_MM_X_MIN"))
                BLIND_DISTANCE = int(request.form.get("BLIND_DISTANCE"))
                SENSOR_KEY = request.form.get("SENSOR_KEY", '')
                HOURS_OFF = request.form.get("HOURS_OFF", '')
                WATER_COST_PER_M3 = request.form.get("WATER_COST_PER_M3", str(settings.DEFAULT_WATER_COST_PER_M3))
                RELAY_POWER_WATTS = request.form.get("RELAY_POWER_WATTS", str(settings.DEFAULT_RELAY_POWER_WATTS))
                ENERGY_COST_PER_KWH = request.form.get("ENERGY_COST_PER_KWH", str(settings.DEFAULT_ENERGY_COST_PER_KWH))
                CURRENCY_CODE = request.form.get("CURRENCY_CODE", settings.DEFAULT_RELAY_CURRENCY)

                HOURS_OFF = bleach.clean(HOURS_OFF)
                SENSOR_KEY = bleach.clean(SENSOR_KEY)
                WATER_COST_PER_M3 = bleach.clean(str(WATER_COST_PER_M3))
                RELAY_POWER_WATTS = bleach.clean(str(RELAY_POWER_WATTS))
                ENERGY_COST_PER_KWH = bleach.clean(str(ENERGY_COST_PER_KWH))
                CURRENCY_CODE = bleach.clean(str(CURRENCY_CODE)).strip().upper()

                try:
                    WATER_COST_PER_M3 = float(WATER_COST_PER_M3)
                    RELAY_POWER_WATTS = float(RELAY_POWER_WATTS)
                    ENERGY_COST_PER_KWH = float(ENERGY_COST_PER_KWH)
                except Exception:
                    flash("Invalid cost/energy values", category='danger')
                    return redirect(url_for('device_info') + '?public_key=' + public_key)

                if ALGO > 1 or ALGO < 0:
                    flash("Invalid ALGO value. ALGO can be 0 or 1", category='danger')
                    return redirect(url_for('device_info') + '?public_key=' + public_key)
                if START_LEVEL > 100 or START_LEVEL < 0:
                    flash("Invalid START_LEVEL value. START_LEVEL should be between 0 and 100 %", category='danger')
                    return redirect(url_for('device_info') + '?public_key=' + public_key)
                if END_LEVEL > 100 or END_LEVEL < 0:
                    flash("Invalid END_LEVEL value. END_LEVEL should be between 0 and 100 %", category='danger')
                    return redirect(url_for('device_info') + '?public_key=' + public_key)
                if END_LEVEL <= START_LEVEL:
                    flash("START_LEVEL % should be lower than END_LEVEL %", category='danger')
                    return redirect(url_for('device_info') + '?public_key=' + public_key)
                if AUTO_OFF > 0:
                    AUTO_OFF = 1
                if AUTO_ON > 0:
                    AUTO_ON = 1
                if MIN_FLOW_MM_X_MIN > 120:
                    flash("FLOW_CHECK_MIN, should be lower than 120 minutes.", category='danger')
                    return redirect(url_for('device_info') + '?public_key=' + public_key)
                if BLIND_DISTANCE < 0:
                    flash("Blind distance, should be >= 0", category='danger')
                    return redirect(url_for('device_info') + '?public_key=' + public_key)
                if WATER_COST_PER_M3 < 0:
                    flash("Water cost per m3 should be >= 0", category='danger')
                    return redirect(url_for('device_info') + '?public_key=' + public_key)
                if RELAY_POWER_WATTS < 0:
                    flash("Relay power watts should be >= 0", category='danger')
                    return redirect(url_for('device_info') + '?public_key=' + public_key)
                if ENERGY_COST_PER_KWH < 0:
                    flash("Energy cost per kWh should be >= 0", category='danger')
                    return redirect(url_for('device_info') + '?public_key=' + public_key)
                if CURRENCY_CODE not in supported_currency_codes:
                    flash("Unsupported currency code", category='danger')
                    return redirect(url_for('device_info') + '?public_key=' + public_key)
                if HOURS_OFF:
                    HOURS_OFF = HOURS_OFF.strip().replace(" ", "")
                    if not db.valid_hours_list(HOURS_OFF):
                        flash("Invalid Disabled Hours, check the format!", category='danger')
                        return redirect(url_for('device_info') + '?public_key=' + public_key)

                if db.DevicesDB.update_relay_settings(device_id, ALGO, START_LEVEL, END_LEVEL, AUTO_OFF, AUTO_ON,
                                                      MIN_FLOW_MM_X_MIN, SENSOR_KEY, BLIND_DISTANCE, HOURS_OFF, SAFE_MODE,
                                                      WATER_COST_PER_M3, RELAY_POWER_WATTS, ENERGY_COST_PER_KWH,
                                                      CURRENCY_CODE):
                    flash("Setting update success", category='success')
                    return redirect(url_for('device_info')+'?public_key='+public_key)
                else:
                    flash("Setting update failed!", category='danger')
                    return redirect(url_for('device_info') + '?public_key=' + public_key)
    elif action == 'sensor-setting' and auth:
        if public_key:
            device = db.DevicesDB.load_device_by_public_key(public_key)
            if device and device.id:
                device_id = device.id
                EMPTY_LEVEL = int(request.form.get("EMPTY_LEVEL"))
                TOP_MARGIN = int(request.form.get("TOP_MARGIN"))
                WIFI_POOL_TIME = int(request.form.get("WIFI_POOL_TIME"))
                MIN_MARGIN = 20
                if int(device.type) == 2:
                    MIN_MARGIN = 2

                if EMPTY_LEVEL > 800:
                    flash("EMPTY_LEVEL can't be bigger than 8 meters (800 CM)!", category='danger')
                    return redirect(url_for('device_info') + '?public_key=' + public_key)
                if EMPTY_LEVEL <= MIN_MARGIN:
                    flash(f"EMPTY_LEVEL can't be lower than {MIN_MARGIN} centimeters!", category='danger')
                    return redirect(url_for('device_info') + '?public_key=' + public_key)

                if TOP_MARGIN < MIN_MARGIN:
                    flash(f"TOP_MARGIN can't be lower than {MIN_MARGIN} centimeters (blind area)!", category='danger')
                    return redirect(url_for('device_info') + '?public_key=' + public_key)

                if TOP_MARGIN >= EMPTY_LEVEL:
                    flash("EMPTY_LEVEL can't be lower than TOP_MARGIN!", category='danger')
                    return redirect(url_for('device_info') + '?public_key=' + public_key)

                min_freq = 30

                if WIFI_POOL_TIME < min_freq:
                    flash(f"WIFI_POOL_TIME can't be lower than {min_freq} seconds.", category='danger')
                    return redirect(url_for('device_info') + '?public_key=' + public_key)

                if WIFI_POOL_TIME > 432000:
                    flash("WIFI_POOL_TIME can't be bigger than 5 days (432000 seconds).", category='danger')
                    return redirect(url_for('device_info') + '?public_key=' + public_key)
                # Parse optional liters-per-cm field from the form and validate
                LITERS_PER_CM = request.form.get("LITERS_PER_CM")
                if LITERS_PER_CM is not None and LITERS_PER_CM != '':
                    try:
                        LITERS_PER_CM = float(LITERS_PER_CM)
                        if LITERS_PER_CM <= 0:
                            flash("LITERS_PER_CM must be greater than 0", category='danger')
                            return redirect(url_for('device_info') + '?public_key=' + public_key)
                    except Exception:
                        flash("Invalid LITERS_PER_CM value", category='danger')
                        return redirect(url_for('device_info') + '?public_key=' + public_key)

                if db.DevicesDB.update_sensor_settings(device_id, EMPTY_LEVEL, TOP_MARGIN, WIFI_POOL_TIME, LITERS_PER_CM):
                    flash("Setting update success", category='success')
                    return redirect(url_for('device_info')+'?public_key='+public_key)
                else:
                    flash("Setting update failed!", category='danger')
                    return redirect(url_for('device_info') + '?public_key=' + public_key)

    flash("Setting update failed!", category='danger')
    return jsonify({'error': 'invalid key'}), 404



@app.route('/data-api', methods=['GET'])
def get_device_data():
    """Return device chart and status data as JSON for dashboard polling.

    Returns:
        flask.Response: JSON response with device metrics.
    """
    key = request.args.get('key')
    if not key:
        return jsonify({'error': 'missing key'}), 400

    # Support shorthand demo alias used by the public UI: map 'demo' to configured demo public key
    if key == 'demo':
        key = settings.DEMO_S1_PUB_KEY

    cache_key = f'tin-keys/{key}'
    result = redis_client.get(cache_key)
    if not result:
        return jsonify({'error': 'invalid key'}), 404

    # Parse cached tuple: distance|rtime|voltage|rssi
    try:
        distance, rtime, voltage, rssi = result.split("|")
        voltage = float(voltage) / 100.0
        diff_time = int(time.time()) - int(rtime)
    except Exception:
        return jsonify({'error': 'invalid cache format'}), 500

    setting_key = f'tin-sett-keys/{key}'
    srv_sett = redis_client.get(setting_key)
    if srv_sett:
        srv_sett = srv_sett.split("|")

    # Try to enrich with DB sensor settings (new liters_per_cm field)
    liters_per_cm = 10.0
    empty_level = None
    top_margin = None
    try:
        device = db.DevicesDB.load_device_by_public_key(key)
        if device:
            sensor_settings = db.DevicesDB.load_device_settings(device.id, device.type)
            if sensor_settings:
                liters_per_cm = float(sensor_settings.get('liters_per_cm', liters_per_cm))
                if sensor_settings.get('EMPTY_LEVEL') is not None:
                    empty_level = int(sensor_settings.get('EMPTY_LEVEL'))
                if sensor_settings.get('TOP_MARGIN') is not None:
                    top_margin = int(sensor_settings.get('TOP_MARGIN'))
    except Exception:
        logging.exception('Failed loading sensor settings from DB')

    # Fallback to redis srv_sett format if DB settings not available
    if empty_level is None and srv_sett and len(srv_sett) >= 2:
        try:
            empty_level = int(srv_sett[0])
            top_margin = int(srv_sett[1])
        except Exception:
            pass

    # Compute current liters if we have the necessary values
    current_liters = None
    water_height_cm = None
    try:
        dist_val = float(distance)
        if empty_level is not None and top_margin is not None:
            if dist_val > empty_level:
                dist_val = empty_level
            if dist_val < top_margin:
                dist_val = top_margin
            water_height_cm = empty_level - dist_val
            if water_height_cm < 0:
                water_height_cm = 0
            current_liters = round(water_height_cm * liters_per_cm, 2)
    except Exception:
        # keep current_liters as None if parsing fails
        pass

    data = {
        'distance': distance,
        'rtime': rtime,
        'skey': key,
        'device_setting': srv_sett,
        'diff_time': diff_time,
        'voltage': round(voltage, 2),
        'rssi': rssi,
        'liters_per_cm': liters_per_cm,
        'empty_level': empty_level,
        'top_margin': top_margin,
        'water_height_cm': water_height_cm,
        'current_liters': current_liters
    }
    return jsonify(data)


@app.route('/ping')
def ping():
    """Expose a lightweight health endpoint used by smoke tests and monitoring.

    Returns:
        str: Health-check marker text.
    """
    return 'PONG'


@app.route('/release-version')
def release_version():
    """Expose web app release version for diagnostics and deployment checks.

    Returns:
        flask.Response: JSON metadata with web release version.
    """
    return jsonify({
        "service": "web",
        "release_version": RELEASE_VERSION
    })


@app.route('/devices', methods=['GET', 'POST'], strict_slashes=False)
@app.route('/<lang>/devices', methods=['GET', 'POST'], strict_slashes=False)
@ensure_language
def devices(lang='en'):
    """Render the authenticated user device list view.

    Args:
        lang: Active locale used in localized routes.

    Returns:
        flask.Response: Rendered devices page.
    """
    if request.method == 'POST' and current_user.is_authenticated:
        action = request.form.get("action")
        public_key = request.form.get("public_key")
        logging.warning(f"request.form: {request.form}")
        if action == 'remove':
            current_user.remove_device(public_key)
            return jsonify({'status': 'success'})
        if action == 'add':
            name = request.form.get("name", '')
            current_user.add_device(public_key, name=name)
            return jsonify({'status': 'success'})
    elif request.method == 'POST':
        return jsonify({'status': 'fail'})
    else:
        return render_template('devices.html')


@app.route('/products/<product_name>', methods=['GET'], strict_slashes=False)
@app.route('/<lang>/products/<product_name>', methods=['GET', 'POST'], strict_slashes=False)
@ensure_language
def products(product_name, lang='en'):
    """Render a localized product information page for a supported product slug.

    Args:
        product_name: Product slug from route.
        lang: Active locale used in localized routes.

    Returns:
        flask.Response: Rendered product page or 404.
    """
    template = "products/s1.html".lower()
    if product_name.lower() == 'WiFi-Water-Level-S1'.lower():
        template = "products/s1.html"
    elif product_name.lower() == 'Solar-Power-Module-P1'.lower():
        return redirect("/products/WiFi-Water-Level-S1")
    elif product_name.lower() == 'WiFi-Smart-Water-Pump-Controller-S1'.lower():
        template = "products/r1.html"

    return render_template(template, UNLOCK_PRICE=0, SUBS_PRICES={}, active_subs=[])

@app.route('/manuals/<product_name>', methods=['GET'], strict_slashes=False)
@app.route('/<lang>/manuals/<product_name>', methods=['GET'], strict_slashes=False)
@ensure_language
def manuals(product_name, lang='en'):
    """Render a localized product manual page for a supported product slug.

    Args:
        product_name: Product slug from route.
        lang: Active locale used in localized routes.

    Returns:
        flask.Response: Rendered manual page or 404.
    """
    template = "manuals/s1.html".lower()
    if product_name.lower() == 'WiFi-Water-Level-S1'.lower():
        template = "manuals/s1.html"
    elif product_name.lower() == 'Solar-Power-Module-P1'.lower():
        return redirect("/products/WiFi-Water-Level-S1")
    elif product_name.lower() == 'WiFi-Smart-Water-Pump-Controller-S1'.lower():
        template = "manuals/r1.html"

    return render_template(template, UNLOCK_PRICE=0, SUBS_PRICES={}, active_subs=[])


@app.route('/ipn-routes-83', methods=['GET', 'POST'])
def IPN():
    """Receive and process incoming payment IPN notifications.

    Returns:
        str: Plain-text status response.
    """
    return jsonify(status='disabled', message='Payment processing has been removed in open-source mode.'), 410


def process_ipn(ipn_message):
    """Parse and persist IPN payload fields into the payment audit store.

    Args:
        ipn_message: Parsed IPN key-value payload.

    Returns:
        None.
    """
    return False



@app.route('/robots.txt')
def robots_txt():
    """Serve robots.txt from static assets.

    Returns:
        flask.Response: Static file response.
    """
    return send_from_directory(app.static_folder, 'robots.txt')

@app.route('/favicon.ico')
def favicon():
    """Serve site favicon from static assets.

    Returns:
        flask.Response: Static file response.
    """
    return send_from_directory(app.static_folder, 'logos/waterlevel.pro-icon.ico')


@app.route('/sitemap.xml')
def sitemap_txt():
    """Serve XML sitemap from static assets.

    Returns:
        flask.Response: Static file response.
    """
    return send_from_directory(app.static_folder, 'sitemap.xml')


@app.route('/image-sitemap.xml')
def image_sitemap_txt():
    """Serve image sitemap from static assets.

    Returns:
        flask.Response: Static file response.
    """
    return send_from_directory(app.static_folder, 'image-sitemap.xml')


@app.route('/ads.txt')
@app.route('/Ads.txt')
def ads_txt():
    """Serve ads.txt from static assets.

    Returns:
        flask.Response: Static file response.
    """
    return send_from_directory(app.static_folder, 'Ads.txt')


@app.route('/contact', methods=['GET', 'POST'], strict_slashes=False)
@app.route('/<lang>/contact', methods=['GET', 'POST'], strict_slashes=False)
@ensure_language
@login_required
def contact(lang='en'):
    """Handle contact form submissions and support message persistence.

    Args:
        lang: Active locale used in localized routes.

    Returns:
        flask.Response: Rendered contact page or redirect.
    """
    sent = False
    if request.method == 'POST':
        reason = request.form['reason']
        device_type = request.form['device_type']
        recaptcha_response = request.form['g-recaptcha-response']
        email = request.form.get('email')
        message = request.form.get('message', '')
        message = message[:500]
        auth_user = False
        if current_user.is_authenticated:
            email = current_user.username
            auth_user = True

        # Validate reCAPTCHA response
        is_valid_recaptcha = validate_recaptcha(recaptcha_response)

        if not is_valid_recaptcha:
            flash('Invalid recaptcha', 'warning')

        # email validation
        valid = validate_email(email)
        email = valid.email

        # Clean data remove any unsafe HTML
        message = bleach.clean(message)
        device_type = bleach.clean(device_type)
        reason = bleach.clean(reason)

        email_body = f""" <h4>Customer Contact Form Used</h4>
        <h5>User Email: {email} | auth_user: {auth_user}</h5>
        <h5>Reasonl: {reason}</h5>
        <h5>Device Type: {device_type}</h5>
        <h5>Message: </h5>
        <p>{message}</p>
        """
        db.Support.add_user_support_record(user_email=email, message=email_body, support_type=0)

        cache_key = f'users_support'
        result = redis_client.incr(cache_key)
        expiration_time = 7 * 24 * 60 * 60  # 7 days in seconds
        redis_client.expire(cache_key, expiration_time)
        sent = True
        flash("Thanks for reaching out to support! We'll review your message and send a response to your email within 2 business days.", 'warning')

    return render_template('contact.html', RECAPTCHA_PUBLIC_KEY=RECAPTCHA_PUBLIC_KEY, sent=sent)


# Route to view HTML report
@app.route('/reportes/<filename>')
@admin_login_required
def view_report(filename):
    """Serve generated analytics reports from the reports directory.

    Args:
        filename: Report filename requested by the client.

    Returns:
        flask.Response: File response or 404.
    """
    report_filename = 'report.html'  # Report filename
    try:
        with open(f'{settings.REPORTS_FOLDER}/{filename}', 'rb') as file:
            content = file.read().decode("utf-8", errors="ignore") 
        return content
    except FileNotFoundError:
        return "Report not found", 404


@app.route('/set_language/<language>')
def set_language(language):
    # Build response
    """Store selected language in cookie and redirect back to referrer page.

    Args:
        language: Target locale code.

    Returns:
        flask.Response: Redirect response with updated cookie.
    """
    normalized_language = normalize_language_code(language)
    resp = make_response(redirect(request.referrer or '/'))  # Redirect to previous URL or '/' if missing
    resp.set_cookie('lang', normalized_language)  # Store selected language in cookie
    return resp


@app.route('/short/<short_code>', methods=['GET'], strict_slashes=False)
def short(short_code):
    """Resolve and redirect short links to their destination URL.

    Args:
        short_code: Short-link identifier from route.

    Returns:
        flask.Response: Redirect response or 404.
    """
    if short_code == "sunbuddy":
        return redirect("https://pro.easyeda.com/editor#id=a14129a4c1e049319308b75c967798a8,tab=*fc869bda6bfd418a8f1333c83e32ca45@a14129a4c1e049319308b75c967798a8")
    if short_code == "smartswitch":
        return redirect("https://pro.easyeda.com/editor#id=b09329c6c6844f6a86d38d3c66eaa65c,tab=*f187656f08184dd5a2dfd13a252b3234@b09329c6c6844f6a86d38d3c66eaa65c")
    return redirect("/")


if __name__ == '__main__':
    #app.run(ssl_context=('./ext_conf/cloudflare/cert.pem', './ext_conf/cloudflare/key.pem'), host='0.0.0.0', port=443, debug=True)
    app.run(debug=True, port=80)
