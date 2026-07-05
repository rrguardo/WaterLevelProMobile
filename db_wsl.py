import time
import re
import datetime

from sqlalchemy import create_engine, Column, Integer, String, text, inspect
from flask_login import UserMixin
from flask_caching import Cache
import settings
import logging
class AttrDict(dict):
    """Dictionary that supports attribute access and `.get()` like a normal dict.

    Accessing missing attributes returns None (via dict.get).
    """
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            return None

    def __setattr__(self, name, value):
        self[name] = value


# Create a database engine using WAL2 mode (Write-Ahead Logging 2)
engine = create_engine(settings.DATABASE_URL, echo=False)
cache = Cache(config=settings.API_CACHE_SETT)


@cache.memoize(300)
def get_user_by_id(id):
    """Fetch a user row by internal user identifier.

    Args:
        id: Numeric user id in the `users` table.

    Returns:
        Row | None: User record when found, otherwise None.
    """
    with engine.connect() as connection:
        query = "SELECT id, email, passw, is_admin, phone FROM users WHERE id = :id"
        result = connection.execute(text(query), {"id": id})
        row = result.fetchone()

        result.close()
        connection.close()
        if row:
            return row


@cache.memoize(300)
def get_user_by_email(email):
    """Fetch a user row by email address.

    Args:
        email: User email to search in the `users` table.

    Returns:
        Row | None: Matching user record when found, otherwise None.
    """
    with engine.connect() as connection:
        query = "SELECT id, email, passw, is_admin, phone FROM users WHERE email = :email"
        result = connection.execute(text(query), {"email": email})
        row = result.fetchone()

        result.close()
        connection.close()
        if row:
            return row


def valid_4register(user_email):
    """Check whether an email is available for registration.

    Args:
        user_email: Email candidate submitted by the user.

    Returns:
        bool: True when registration is allowed for that email.
    """
    with engine.connect() as connection:
        query = "SELECT confirmed FROM users WHERE email = :user_email"
        result = connection.execute(text(query), {"user_email": user_email})
        row = result.fetchone()

        result.close()
        connection.close()
        if row:
            return row.confirmed == 0
    return True


def valid_hours_list(hours_list):
    # Regular expression to validate list of numbers between 0 and 23 separated by commas
    """Validate relay disabled-hours format (`0-23` comma-separated list).

    Args:
        hours_list: String with hour numbers separated by commas.

    Returns:
        bool: True when the input matches the expected hour-list pattern.
    """
    pattern = r'^(?:[0-9]|1[0-9]|2[0-3])(?:,(?:[0-9]|1[0-9]|2[0-3]))*$'
    return bool(re.fullmatch(pattern, hours_list))


def add_user(email, passw_hash):
    """Insert a new non-admin user record.

    Args:
        email: User email to persist.
        passw_hash: SHA-256 hashed password string.

    Returns:
        bool: True when the insert/update succeeds.
    """
    sql_query = """
        INSERT OR REPLACE INTO users (email, passw, is_admin, confirmed) 
        VALUES (:email, :passw, 0, 0)
    """
    with engine.connect() as connection:
        result = connection.execute(text(sql_query), {"email": email, "passw": passw_hash})
        connection.commit()
        if result:
            return True
    return False


def confirm_user(email):
    """Mark a user account as email-confirmed.

    Args:
        email: User email to update.

    Returns:
        bool: True when the confirmation flag is updated.
    """
    sql_query = """
            UPDATE users 
                SET confirmed=1
            WHERE email = :email
        """
    with engine.connect() as connection:
        result = connection.execute(text(sql_query), {"email": email})
        connection.commit()
        if result:
            return True
    return False


def try_login(email, passw):
    """Retrieve a user row for login credential verification.

    Args:
        email: Email provided at login.
        passw: Stored-hash candidate to compare.

    Returns:
        Row | None: Matching user row when credentials are valid.
    """
    connection = engine.connect()

    query = "SELECT id, email, passw, is_admin, confirmed FROM users WHERE email = :email AND passw = :passw"
    result = connection.execute(text(query), {"email": email, "passw": passw})
    row = result.fetchone()

    result.close()
    connection.close()
    if row:
        return row


class PP_IPN:
    """Store PayPal IPN helper constants and persistence utilities."""
    Payments_Status = ["Completed", "Pending", "Denied", "Refunded", "Reversed"]
    Valid_Product_Names = []

    SUBS_PRICES = {}

    UNLOCK_PRICE = 0

    @staticmethod
    def get_subs_name_id(item_name):
        return 0

    @staticmethod
    def product_name_price(item_name):
        return 0

    @staticmethod
    def ipn_status(txn_id):
        connection = engine.connect()
        query = """
            SELECT payment_status 
                FROM pp_ipn 
            WHERE txn_id=:txn_id 
        """
        result = connection.execute(text(query), {"txn_id": txn_id})
        row = result.fetchone()

        result.close()
        connection.close()
        if row and row.payment_status:
            return row.payment_status
        return False

    @staticmethod
    def add_pp_ipn(txn_id, payment_status, receiver_email, payer_email, amount, custom, receiver_id, item_name):
        sql_query = """
                    INSERT OR REPLACE INTO pp_ipn (txn_id, payment_status, receiver_email, payer_email, amount, custom, receiver_id, item_name) 
                        VALUES (:txn_id, :payment_status, :receiver_email, :payer_email, :amount, :custom, :receiver_id, :item_name)
                """
        with engine.connect() as connection:
            result = connection.execute(text(sql_query), {
                "txn_id": txn_id, "payment_status": payment_status, "receiver_email": receiver_email,
                "payer_email": payer_email, "amount": amount, "custom": custom, "receiver_id": receiver_id,
                "item_name": item_name
            })
            connection.commit()
            if result:
                return True
        return False

class CronsDB:
    """Expose query helpers used by email/SMS alert cron jobs."""

    @staticmethod
    def get_email_alerts_info():
        connection = engine.connect()
        query = ("""
                    SELECT ua.condition, ua.level, ua.device_id, ua.user_id, u.email, IFNULL(us_freq.setting_value, 6) AS frequency 
                      FROM user_alerts ua
                        LEFT JOIN user_settings us 
                            ON us.user_id=ua.user_id
                        LEFT JOIN users u
                            ON u.id=ua.user_id
                        LEFT JOIN user_settings us_freq 
                            ON us_freq.user_id=ua.user_id AND us_freq.setting_name='frequency-alert'
                    WHERE us.setting_name = 'email-alert' AND us.setting_value = 'on'
                    ORDER BY ua.condition DESC
                """)
        result = connection.execute(text(query))
        rows = result.fetchall()

        result.close()
        connection.close()
        return rows

    @staticmethod
    def get_sms_alerts_info():
        connection = engine.connect()
        query = ("""
                    SELECT ua.condition, ua.level, ua.device_id, ua.user_id, u.phone, IFNULL(us_freq.setting_value, 6) AS frequency 
                      FROM user_alerts ua
                        LEFT JOIN user_settings us 
                            ON us.user_id=ua.user_id
                        LEFT JOIN users u
                            ON u.id=ua.user_id
                        LEFT JOIN user_settings us_freq 
                            ON us_freq.user_id=ua.user_id AND us_freq.setting_name='frequency-alert'
                    WHERE us.setting_name = 'sms-alert' AND us.setting_value = 'on' AND u.phone > 0
                    ORDER BY ua.condition DESC
                    """)
        result = connection.execute(text(query))
        rows = result.fetchall()

        result.close()
        connection.close()
        return rows


class DevicesDB:
    """Provide device-centric read/write operations and cached lookups."""

    @staticmethod
    @cache.memoize(600)
    def get_device_uptime(device_id):
        connection = engine.connect()

        query = "SELECT up_hours FROM device_uptime WHERE device_id = :device_id"
        result = connection.execute(text(query), {"device_id": device_id})
        row = result.fetchone()

        result.close()
        connection.close()
        if row and row.up_hours:
            return row.up_hours
        return 0

    @staticmethod
    def record_uptime(device_id):
        try:
            sql_query = """
            INSERT INTO device_uptime (device_id, up_hours)
            VALUES (:device_id, 1)
            ON CONFLICT(device_id) DO UPDATE SET up_hours = up_hours + 1;
            """
            inserted_id = None
            with engine.connect() as connection:
                result = connection.execute(
                    text(sql_query), {
                        "device_id": device_id
                    })
                connection.commit()
                if not result:
                    return False
                inserted_id = result.lastrowid
            return True
        except Exception as ex:
            logging.exception(ex)
        return False

    @staticmethod
    @cache.memoize(600)
    def buy_options_subscriptions(device_id):
        return []


    @staticmethod
    @cache.memoize(600)
    def subscriptions(device_id, only_active=False):
        return []

    @staticmethod
    def process_valid_ipn_subscription(subs_type, device_id, is_trial=False):
        return True

    @staticmethod
    @cache.memoize(600)
    def is_unlocked(device_id):
        return True
        connection = engine.connect()

        query = "SELECT at FROM unlocked_devices WHERE device_id = :device_id"
        result = connection.execute(text(query), {"device_id": device_id})
        row = result.fetchone()

        result.close()
        connection.close()
        if row and row.at:
            return True
        return False

    @staticmethod
    def unlock_device(device_id, note='-'):
        return True

    @staticmethod
    @cache.memoize(600)
    def valid_private_key(private_key):
        connection = engine.connect()

        query = "SELECT public_key FROM devices WHERE private_key = :private_key"
        result = connection.execute(text(query), {"private_key": private_key})
        row = result.fetchone()

        result.close()
        connection.close()
        if row and row.public_key:
            return row.public_key
        return False

    @staticmethod
    @cache.memoize(300)
    def load_device_by_public_key(public_key):
        connection = engine.connect()

        query = "SELECT * FROM devices WHERE public_key = :public_key"
        result = connection.execute(text(query), {"public_key": public_key})
        row = result.fetchone()

        result.close()
        connection.close()
        if row:
            return row

    @staticmethod
    @cache.memoize(3000)
    def load_device_id_by_public_key(public_key):
        connection = engine.connect()

        query = "SELECT id FROM devices WHERE public_key = :public_key"
        result = connection.execute(text(query), {"public_key": public_key})
        row = result.fetchone()

        result.close()
        connection.close()
        if row and row.id:
            return row.id

    @staticmethod
    @cache.memoize(300)
    def load_model_info_by_public_key(public_key):
        connection = engine.connect()

        query = "SELECT * FROM devices_types WHERE id IN (SELECT type FROM devices WHERE public_key = :public_key)"
        result = connection.execute(text(query), {"public_key": public_key})
        row = result.fetchone()

        result.close()
        connection.close()
        if row:
            return row

    @staticmethod
    @cache.memoize(300)
    def load_device_settings(device_id, device_type=1):
        if device_type == 3:
            return DevicesDB.load_relay_settings(device_id)
        connection = engine.connect()

        query = "SELECT * FROM sensor_settings WHERE device = :device_id"
        result = connection.execute(text(query), {"device_id": device_id})
        row = result.fetchone()

        result.close()
        connection.close()
        if row:
            # Ensure liters_per_cm is present and has default if None
            row_dict = dict(row._mapping) if hasattr(row, '_mapping') else dict(row)
            # Ensure `liters_per_cm` exists with a sensible default
            if 'liters_per_cm' not in row_dict or row_dict['liters_per_cm'] is None:
                row_dict['liters_per_cm'] = 10.0
            # Return a dict-like object that supports attribute access and `.get()`
            return AttrDict(row_dict)
        return None

    @staticmethod
    def load_s1_info(device_id):
        # no cache because used by cron
        connection = engine.connect()

        query = """
            SELECT dv.public_key, ss.WIFI_POOL_TIME, ss.EMPTY_LEVEL, ss.TOP_MARGIN 
                FROM devices dv
                LEFT JOIN sensor_settings ss 
                    ON ss.device = dv.id
            WHERE dv.id = :device_id
            """
        result = connection.execute(text(query), {"device_id": device_id})
        row = result.fetchone()

        result.close()
        connection.close()
        if row:
            return row

    @staticmethod
    @cache.memoize(300)
    def load_relay_settings(device_id):
        table_exists = DevicesDB.ensure_relay_settings_extra_fields()
        if not table_exists:
            return None
        connection = engine.connect()

        query = "SELECT * FROM relay_settings WHERE device = :device_id"
        result = connection.execute(text(query), {"device_id": device_id})
        row = result.fetchone()

        result.close()
        connection.close()
        if row:
            # Normalize relay settings rows to a dict-like object that supports
            # both attribute access and `.get(...)`.
            if isinstance(row, dict):
                row_dict = dict(row)
            elif hasattr(row, '_mapping'):
                row_dict = dict(row._mapping)
            else:
                try:
                    row_dict = dict(row)
                except Exception:
                    try:
                        row_dict = vars(row)
                    except Exception:
                        return row
            return AttrDict(row_dict)

    @staticmethod
    def ensure_relay_settings_extra_fields():
        """Ensure relay_settings has optional cost/energy columns.

        Adds backward-compatible columns when running on existing databases.
        """
        sql_columns = "PRAGMA table_info(relay_settings)"
        expected_columns = {
            "WATER_COST_PER_M3": f"REAL NOT NULL DEFAULT {float(settings.DEFAULT_WATER_COST_PER_M3)}",
            "RELAY_POWER_WATTS": f"REAL NOT NULL DEFAULT {float(settings.DEFAULT_RELAY_POWER_WATTS)}",
            "ENERGY_COST_PER_KWH": f"REAL NOT NULL DEFAULT {float(settings.DEFAULT_ENERGY_COST_PER_KWH)}",
            "CURRENCY_CODE": f"TEXT NOT NULL DEFAULT '{settings.DEFAULT_RELAY_CURRENCY}'"
        }

        with engine.connect() as connection:
            table_row = connection.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='relay_settings'")
            ).fetchone()
            if not table_row:
                return False

            result = connection.execute(text(sql_columns))
            existing = {row[1] for row in result.fetchall()}
            result.close()

            changed = False
            for col_name, col_sql in expected_columns.items():
                if col_name not in existing:
                    connection.execute(text(f"ALTER TABLE relay_settings ADD COLUMN {col_name} {col_sql}"))
                    changed = True

            if changed:
                connection.commit()

        return True

    @staticmethod
    def update_sensor_settings(device_id, EMPTY_LEVEL=None, TOP_MARGIN=None, WIFI_POOL_TIME=None, LITERS_PER_CM=None):
        # Build dynamic query based on present fields
        fields = ["device"]
        values = {"device": device_id}
        if EMPTY_LEVEL is not None:
            fields.append("EMPTY_LEVEL")
            values["EMPTY_LEVEL"] = EMPTY_LEVEL
        if TOP_MARGIN is not None:
            fields.append("TOP_MARGIN")
            values["TOP_MARGIN"] = TOP_MARGIN
        if WIFI_POOL_TIME is not None:
            fields.append("WIFI_POOL_TIME")
            values["WIFI_POOL_TIME"] = WIFI_POOL_TIME
        if LITERS_PER_CM is not None:
            fields.append('liters_per_cm')
            values['liters_per_cm'] = LITERS_PER_CM
        sql_query = f"""
            INSERT OR REPLACE INTO sensor_settings ({', '.join(fields)})
                VALUES ({', '.join(':' + f for f in fields)})
        """
        with engine.connect() as connection:
            result = connection.execute(text(sql_query), values)
            connection.commit()
            if result:
                cache.delete_memoized(DevicesDB.load_device_settings, device_id, 1)
                cache.delete_memoized(DevicesDB.load_device_settings, device_id, 2)
                return True
        return False

    @staticmethod
    def update_sensor_pool_time(device_id, WIFI_POOL_TIME):
        sql_query = """
                UPDATE sensor_settings 
                    SET WIFI_POOL_TIME= :WIFI_POOL_TIME
                WHERE device= :device
            """
        with engine.connect() as connection:
            result = connection.execute(text(sql_query), {
                "device": device_id, "WIFI_POOL_TIME": WIFI_POOL_TIME})
            connection.commit()
            if result:
                cache.delete_memoized(DevicesDB.load_device_settings, device_id, 1)
                return True
        return False

    @staticmethod
    def update_relay_settings(device_id, ALGO=0, START_LEVEL=30, END_LEVEL=95, AUTO_OFF=1, AUTO_ON=1,
                              MIN_FLOW_MM_X_MIN=10, SENSOR_KEY='', BLIND_DISTANCE=22, HOURS_OFF='', SAFE_MODE=1,
                              WATER_COST_PER_M3=settings.DEFAULT_WATER_COST_PER_M3,
                              RELAY_POWER_WATTS=settings.DEFAULT_RELAY_POWER_WATTS,
                              ENERGY_COST_PER_KWH=settings.DEFAULT_ENERGY_COST_PER_KWH,
                              CURRENCY_CODE=settings.DEFAULT_RELAY_CURRENCY):
        table_exists = DevicesDB.ensure_relay_settings_extra_fields()
        if not table_exists:
            return False
        sql_query = """
                INSERT OR REPLACE INTO relay_settings 
                    (device, ALGO, START_LEVEL, END_LEVEL, AUTO_OFF, AUTO_ON, MIN_FLOW_MM_X_MIN, 
                    SENSOR_KEY, BLIND_DISTANCE, HOURS_OFF, SAFE_MODE,
                    WATER_COST_PER_M3, RELAY_POWER_WATTS, ENERGY_COST_PER_KWH, CURRENCY_CODE) 
                    
                    VALUES (:device, :ALGO, :START_LEVEL, :END_LEVEL, :AUTO_OFF, :AUTO_ON, :MIN_FLOW_MM_X_MIN, 
                    :SENSOR_KEY, :BLIND_DISTANCE, :HOURS_OFF, :SAFE_MODE,
                    :WATER_COST_PER_M3, :RELAY_POWER_WATTS, :ENERGY_COST_PER_KWH, :CURRENCY_CODE)
            """
        with engine.connect() as connection:
            result = connection.execute(text(sql_query), {
                "device": device_id, "ALGO": ALGO, "START_LEVEL": START_LEVEL,
                "END_LEVEL": END_LEVEL, "AUTO_OFF": AUTO_OFF, "AUTO_ON": AUTO_ON,
                "MIN_FLOW_MM_X_MIN": MIN_FLOW_MM_X_MIN, "SENSOR_KEY": SENSOR_KEY,
                "BLIND_DISTANCE": BLIND_DISTANCE, "HOURS_OFF": HOURS_OFF, "SAFE_MODE": SAFE_MODE,
                "WATER_COST_PER_M3": float(max(0.0, WATER_COST_PER_M3)),
                "RELAY_POWER_WATTS": float(max(0.0, RELAY_POWER_WATTS)),
                "ENERGY_COST_PER_KWH": float(max(0.0, ENERGY_COST_PER_KWH)),
                "CURRENCY_CODE": str(CURRENCY_CODE or settings.DEFAULT_RELAY_CURRENCY).strip().upper()
            })
            connection.commit()
            if result:
                cache.delete_memoized(DevicesDB.load_device_settings, device_id, 3)
                cache.delete_memoized(DevicesDB.load_relay_settings, device_id)

                return True
        return False

    @staticmethod
    def turn_off_relay_smart_mode(device_id):
        sql_query = """
                    UPDATE relay_settings 
                        SET ALGO=0
                    WHERE device= :device
                """
        with engine.connect() as connection:
            result = connection.execute(text(sql_query), {
                "device": device_id
            })
            connection.commit()
            if result:
                cache.delete_memoized(DevicesDB.load_device_settings, device_id, 3)
                cache.delete_memoized(DevicesDB.load_relay_settings, device_id)

                return True
        return False

    @staticmethod
    @cache.memoize(300)
    def get_user_device_name(user_id, public_key):
        connection = engine.connect()

        query = ("SELECT ud.name AS name FROM user_devices ud "
                 "LEFT JOIN devices dv ON ud.device_id=dv.id "
                 "WHERE ud.user_id = :user_id "
                 " AND dv.public_key = :public_key ")
        result = connection.execute(text(query), {"user_id": user_id, "public_key": public_key})
        row = result.fetchone()

        result.close()
        connection.close()
        if row and row.name:
            return row.name
        return ''

    @staticmethod
    @cache.memoize(300)
    def user_can_admin_device(user_id, public_key):
        connection = engine.connect()

        query = ("SELECT ud.can_admin AS can_admin FROM user_devices ud "
                 "LEFT JOIN devices dv ON ud.device_id=dv.id "
                 "WHERE ud.user_id = :user_id "
                 " AND dv.public_key = :public_key ")
        result = connection.execute(text(query), {"user_id": user_id, "public_key": public_key})
        row = result.fetchone()

        result.close()
        connection.close()
        if row and int(row.can_admin) == 1:
            return True
        return False

    @staticmethod
    def get_all_devices_by_type(device_type):
        connection = engine.connect()

        query = ("SELECT id, public_key, private_key, note FROM devices "
                 "WHERE type = :device_type")
        if device_type == [1, 2]:
            query = ("SELECT id, public_key, private_key, note FROM devices "
                     "WHERE type in (1, 2)")
        result = connection.execute(text(query), {"device_type": device_type})
        rows = result.fetchall()

        result.close()
        connection.close()
        return [{
            "id": r.id, "public_key": r.public_key, "private_key": r.private_key, "note": r.note or '-'
        } for r in rows]

    @staticmethod
    def add_device(private_key, public_key, note, device_type):
        try:
            sql_query = """
                    INSERT INTO devices (private_key, public_key, note, type) 
                    VALUES (:private_key, :public_key, :note, :device_type)
                """
            inserted_id = None
            with engine.connect() as connection:
                result = connection.execute(
                    text(sql_query), {
                        "private_key": private_key, "public_key": public_key,
                        "note": note, "device_type": device_type
                    })
                connection.commit()
                if not result:
                    return False
                inserted_id = result.lastrowid
            if device_type == 1:
                DevicesDB.update_sensor_settings(inserted_id)
            elif device_type == 3:
                DevicesDB.update_relay_settings(inserted_id)
            return True
        except Exception as ex:
            logging.exception(ex)
        return False

    @staticmethod
    @cache.memoize(30)
    def add_relay_events(relay_id, events):
        try:
            past_event = DevicesDB.get_relay_events(relay_id, 1)
            if past_event and events and past_event[0].get("events", "") == events:
                events_int = events.split(',')
                if '1' in events_int or '2' in events_int:
                    return True
            sql_query = """
                        INSERT INTO relay_events (relay_id, events, created_at) 
                        VALUES (:relay_id, :events, :created_at)
                    """
            inserted_id = None
            with engine.connect() as connection:
                result = connection.execute(
                    text(sql_query), {
                        "relay_id": relay_id, "events": events,
                        "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })
                connection.commit()
                if not result:
                    return False
                else:
                    cache.delete_memoized(DevicesDB.get_relay_events, relay_id, 20)
                    cache.delete_memoized(DevicesDB.get_relay_events, relay_id, 1)
            return True
        except Exception as ex:
            logging.exception(ex)
        return False

    @staticmethod
    @cache.memoize(300)
    def get_relay_events(relay_id, total_limit=20):
        connection = engine.connect()

        query = ("SELECT id, events, created_at "
                 "FROM  relay_events "
                 "WHERE relay_id = :relay_id "
                 "ORDER BY id DESC"
                 " LIMIT :total_limit ")
        result = connection.execute(text(query), {"relay_id": relay_id, "total_limit": total_limit})

        if not result:
            return None

        rows = result.fetchall()
        if not rows:
            return None

        result.close()
        connection.close()
        return [{
            "id": r.id, "events": r.events, "created_at": r.created_at
        } for r in rows]

    @staticmethod
    def ensure_relay_daily_stats_table():
        """Ensure the relay daily stats table exists.

        Table stores per-relay daily aggregates for ON runtime and estimated
        liters added while pump is ON.
        """
        sql_create = """
            CREATE TABLE IF NOT EXISTS relay_daily_stats (
                relay_id INTEGER NOT NULL,
                day_date TEXT NOT NULL,
                on_seconds INTEGER NOT NULL DEFAULT 0,
                liters_added REAL NOT NULL DEFAULT 0,
                updated_at TEXT,
                PRIMARY KEY (relay_id, day_date)
            )
        """
        sql_index = """
            CREATE INDEX IF NOT EXISTS idx_relay_daily_stats_day
            ON relay_daily_stats(day_date)
        """
        with engine.connect() as connection:
            connection.execute(text(sql_create))
            connection.execute(text(sql_index))
            connection.commit()

    @staticmethod
    def _upsert_relay_daily_stats(relay_id, day_date, on_seconds_inc=0, liters_added_inc=0.0):
        """Increment per-day aggregate counters for a relay.

        Args:
            relay_id: Relay device id.
            day_date: UTC day key in YYYY-MM-DD format.
            on_seconds_inc: Seconds to add to ON runtime.
            liters_added_inc: Liters to add to estimated daily added water.
        """
        DevicesDB.ensure_relay_daily_stats_table()
        sql_query = """
            INSERT INTO relay_daily_stats (relay_id, day_date, on_seconds, liters_added, updated_at)
            VALUES (:relay_id, :day_date, :on_seconds_inc, :liters_added_inc, :updated_at)
            ON CONFLICT(relay_id, day_date)
            DO UPDATE SET
                on_seconds = on_seconds + excluded.on_seconds,
                liters_added = liters_added + excluded.liters_added,
                updated_at = excluded.updated_at
        """
        with engine.connect() as connection:
            connection.execute(text(sql_query), {
                "relay_id": relay_id,
                "day_date": day_date,
                "on_seconds_inc": int(max(0, on_seconds_inc)),
                "liters_added_inc": float(max(0.0, liters_added_inc)),
                "updated_at": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            })
            connection.commit()

    @staticmethod
    def add_relay_on_runtime(relay_id, start_ts, end_ts):
        """Add relay ON runtime splitting seconds across UTC day boundaries.

        Args:
            relay_id: Relay device id.
            start_ts: Interval start epoch seconds (inclusive).
            end_ts: Interval end epoch seconds (exclusive).
        """
        try:
            start_ts = int(start_ts)
            end_ts = int(end_ts)
        except Exception:
            return

        if end_ts <= start_ts:
            return

        cursor = start_ts
        while cursor < end_ts:
            day_start_dt = datetime.datetime.fromtimestamp(cursor, datetime.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            next_day_dt = day_start_dt + datetime.timedelta(days=1)
            next_day_ts = int(next_day_dt.timestamp())
            chunk_end = min(end_ts, next_day_ts)
            chunk_seconds = max(0, chunk_end - cursor)
            day_key = day_start_dt.strftime("%Y-%m-%d")
            DevicesDB._upsert_relay_daily_stats(relay_id, day_key, on_seconds_inc=chunk_seconds, liters_added_inc=0.0)
            cursor = chunk_end

    @staticmethod
    def add_relay_liters_for_day(relay_id, at_ts, liters_added):
        """Add estimated liters to the UTC day bucket containing `at_ts`."""
        try:
            at_ts = int(at_ts)
            liters_added = float(liters_added)
        except Exception:
            return

        if liters_added <= 0:
            return

        day_key = datetime.datetime.fromtimestamp(at_ts, datetime.timezone.utc).strftime("%Y-%m-%d")
        DevicesDB._upsert_relay_daily_stats(relay_id, day_key, on_seconds_inc=0, liters_added_inc=liters_added)

    @staticmethod
    def get_relay_daily_stats(relay_id, days=15, start_date=None, end_date=None):
        """Return contiguous daily stats for a range or trailing `days` window.

        Missing days are zero-filled to simplify chart rendering.
        """
        DevicesDB.ensure_relay_daily_stats_table()

        if start_date is not None and end_date is not None:
            if isinstance(start_date, str):
                start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
            if isinstance(end_date, str):
                end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
            if end_date < start_date:
                start_date, end_date = end_date, start_date
            days = (end_date - start_date).days + 1
        else:
            try:
                days = int(days)
            except Exception:
                days = 15
            if days < 1:
                days = 1

            end_date = datetime.datetime.utcnow().date()
            start_date = end_date - datetime.timedelta(days=days - 1)

        query = """
            SELECT day_date, on_seconds, liters_added
            FROM relay_daily_stats
            WHERE relay_id = :relay_id
              AND day_date >= :start_date
                            AND day_date <= :end_date
            ORDER BY day_date ASC
        """

        rows_by_day = {}
        with engine.connect() as connection:
            result = connection.execute(text(query), {
                "relay_id": relay_id,
                "start_date": start_date.strftime("%Y-%m-%d"),
                "end_date": end_date.strftime("%Y-%m-%d")
            })
            rows = result.fetchall()
            result.close()

        for row in rows:
            rows_by_day[row.day_date] = {
                "on_seconds": int(row.on_seconds or 0),
                "liters_added": float(row.liters_added or 0.0)
            }

        output = []
        for offset in range(days):
            current = start_date + datetime.timedelta(days=offset)
            day_key = current.strftime("%Y-%m-%d")
            item = rows_by_day.get(day_key, {"on_seconds": 0, "liters_added": 0.0})
            output.append({
                "day": day_key,
                "on_minutes": int(round(item["on_seconds"] / 60.0)),
                "liters": round(item["liters_added"], 2)
            })

        return output


class User(UserMixin):
    """Flask-Login compatible user model backed by SQL helper methods."""
    def __init__(self, id, username, password, is_admin=False):
        self.username = username
        self.password = password
        self.id = id
        self.is_admin = is_admin

    def get_id(self):
        return self.id

    def get_device_name(self, pub_key):
        return DevicesDB.get_user_device_name(self.id, pub_key)

    def can_admin_device(self, pub_key):
        return DevicesDB.user_can_admin_device(self.id, pub_key)

    def get_devices(self):
        return User.load_user_devices(self.id)

    def remove_device(self, public_key):
        sql_query = """
                DELETE FROM user_devices
                WHERE user_id = :user_id AND device_id IN (SELECT id FROM devices WHERE public_key = :public_key)
            """
        with engine.connect() as connection:
            result = connection.execute(text(sql_query), {"user_id": self.id, "public_key": public_key})
            connection.commit()
            cache.delete_memoized(User.load_user_devices, self.id)
            if result:
                return True
        return False

    def add_device(self, public_key, name='', can_admin=0):
        device_info = DevicesDB.load_device_by_public_key(public_key)
        if device_info and device_info.id:
            sql_query = """
                    INSERT OR REPLACE INTO user_devices (user_id, device_id, name, can_admin) 
                        VALUES (:user_id, :device_id, :name, :can_admin)
                """
            with engine.connect() as connection:
                result = connection.execute(text(sql_query), {
                    "user_id": self.id, "device_id": device_info.id, "name": name, "can_admin": can_admin})
                connection.commit()
                cache.delete_memoized(User.load_user_devices, self.id)
                cache.delete_memoized(DevicesDB.get_user_device_name, self.id, public_key)
                cache.delete_memoized(DevicesDB.user_can_admin_device, self.id, public_key)
                if result:
                    return True
        return False

    def add_alert(self, public_key, condition, level):
        device_info = DevicesDB.load_device_by_public_key(public_key)
        if device_info and device_info.id:
            sql_query = """
                    INSERT OR REPLACE INTO user_alerts (user_id, device_id, condition, level) 
                        VALUES (:user_id, :device_id, :condition, :level)
                """
            with engine.connect() as connection:
                result = connection.execute(text(sql_query), {
                    "user_id": self.id, "device_id": device_info.id, "condition": condition, "level": level})
                connection.commit()
                cache.delete_memoized(User.load_device_alerts, self.id, public_key)
                if result:
                    return True
        return False

    def delete_alert(self, public_key, condition, level):
        device_info = DevicesDB.load_device_by_public_key(public_key)
        if device_info and device_info.id:
            sql_query = """
                    DELETE FROM user_alerts 
                    WHERE user_id = :user_id AND device_id = :device_id 
                        AND condition = :condition AND level = :level
                """

            with engine.connect() as connection:
                result = connection.execute(text(sql_query), {
                    "user_id": self.id, "device_id": device_info.id, "condition": condition, "level": level})
                connection.commit()
                cache.delete_memoized(User.load_device_alerts, self.id, public_key)
                if result:
                    return True
        return False

    @staticmethod
    @cache.memoize(300)
    def load_device_alerts(user_id, public_key):
        device_info = DevicesDB.load_device_by_public_key(public_key)
        if device_info and device_info.id:
            device_id = device_info.id
            connection = engine.connect()

            query = ("SELECT condition, level"
                     " FROM user_alerts "
                     "WHERE user_id = :user_id AND device_id = :device_id")
            result = connection.execute(text(query), {"user_id": user_id, "device_id": device_id})
            rows = result.fetchall()

            result.close()
            connection.close()
            return rows

    @staticmethod
    @cache.memoize(300)
    def load_user_devices(user_id):
        connection = engine.connect()

        query = ("SELECT dv.public_key as public_key,  ud.name as name,  ud.can_admin, dv.type, dt.long_name"
                 " FROM user_devices ud "
                 "LEFT JOIN devices dv ON ud.device_id=dv.id "
                 " LEFT JOIN devices_types dt ON dt.id=dv.type "
                 "WHERE ud.user_id = :user_id")
        result = connection.execute(text(query), {"user_id": user_id})
        rows = result.fetchall()

        result.close()
        connection.close()
        return rows

    def set_phone(self, phone):
        sql_query = """
                UPDATE users 
                    SET phone= :phone
                WHERE id = :user_id
            """
        with engine.connect() as connection:
            result = connection.execute(text(sql_query), {"user_id": self.id, "phone": phone})
            connection.commit()

            cache.delete_memoized(get_user_by_id, self.id)
            if result:
                return True
        return False

    def set_setting(self, setting_name, setting_value):
        sql_query = """
                INSERT OR REPLACE INTO user_settings (user_id, setting_name, setting_value) 
                    VALUES (:user_id, :setting_name, :setting_value)
            """
        with engine.connect() as connection:
            result = connection.execute(text(sql_query), {
                "user_id": self.id, "setting_name": setting_name,
                "setting_value": setting_value})
            connection.commit()

            cache.delete_memoized(User.get_user_settings, self.id)
            if result:
                return True
        return False

    @staticmethod
    @cache.memoize(300)
    def get_user_settings(user_id):
        connection = engine.connect()

        query = ("SELECT setting_name, setting_value"
                 " FROM user_settings "
                 "WHERE user_id = :user_id")
        result = connection.execute(text(query), {"user_id": user_id})
        rows = result.fetchall()
        result_dict = {}
        for item in rows:
            result_dict[item.setting_name] = item.setting_value

        result.close()
        connection.close()
        return result_dict

    @staticmethod
    @cache.memoize(300)
    def get_sms_credits(user_id):
        connection = engine.connect()

        query = ("SELECT credits"
                 " FROM user_sms_credits "
                 "WHERE user_id = :user_id")
        result = connection.execute(text(query), {"user_id": user_id})
        row = result.fetchone()

        result.close()
        connection.close()
        if row and row.credits:
            return float(row.credits)
        return 0.0

    @staticmethod
    def add_sms_credits(user_id, amount):
        logging.warning(f"add_sms_credits  user_id: {user_id}, amount: {amount}")
        prev_credits = User.get_sms_credits(user_id)
        total = prev_credits + amount
        sql_query = """
                INSERT OR REPLACE INTO user_sms_credits (user_id, credits) 
                    VALUES (:user_id, :total)
            """
        with engine.connect() as connection:
            result = connection.execute(text(sql_query), {
                "user_id": user_id, "total": total})
            connection.commit()

            cache.delete_memoized(User.get_sms_credits, user_id)
            if result:
                return True
        return False

    @staticmethod
    def consume_sms_credits(user_id, amount):
        logging.warning(f"consume_sms_credits  user_id: {user_id}, amount: {amount}")
        prev_credits = User.get_sms_credits(user_id)
        total = prev_credits + amount
        sql_query = """
                    UPDATE user_sms_credits 
                        SET credits= credits - :amount
                    WHERE user_id= :user_id
                """
        with engine.connect() as connection:
            result = connection.execute(text(sql_query), {
                "user_id": user_id, "amount": amount})
            connection.commit()

            cache.delete_memoized(User.get_sms_credits, user_id)
            if result:
                return True
        return False

    @staticmethod
    def get_all_users():
        connection = engine.connect()

        query = ("SELECT id, email, phone, confirmed FROM users ")
        result = connection.execute(text(query))
        rows = result.fetchall()

        result.close()
        connection.close()
        return [{
            "id": r.id, "email": r.email, "phone": r.phone or 'None', "confirmed": 'yes' if r.confirmed else 'no'
        } for r in rows]


class Support:
    """Support ticket persistence and retrieval helpers."""

    @staticmethod
    def get_all_users_support():
        connection = engine.connect()

        query = ("SELECT id, user_email, message, created_at, support_type"
                 " FROM support_info "
                 "ORDER BY id DESC")
        result = connection.execute(text(query))
        rows = result.fetchall()

        result.close()
        connection.close()
        return [{
            "id": r.id, "email": r.user_email, "message": r.message, "created_at": r.created_at,
            "support_type": "Customer" if r.support_type == 0 else "Support"
        } for r in rows]

    @staticmethod
    @cache.memoize(300)
    def get_user_support(user_email):
        connection = engine.connect()
        user_email = user_email.strip()

        query = ("SELECT id, message, created_at, support_type"
                 " FROM support_info "
                 "WHERE user_email = :user_email "
                 "ORDER BY id DESC")
        result = connection.execute(text(query), {"user_email": user_email})
        rows = result.fetchall()
        return rows

    @staticmethod
    def add_user_support_record(user_email, message, support_type=0):
        # support_type: 0 = sent by user, 1 = sent by support to user
        try:
            user_email = user_email.strip()
            sql_query = """
                    INSERT INTO support_info (user_email, message, support_type) 
                    VALUES (:user_email, :message, :support_type)
                """
            with engine.connect() as connection:
                result = connection.execute(
                    text(sql_query), {
                        "user_email": user_email, "message": message,
                        "support_type": support_type
                    })
                connection.commit()
                cache.delete_memoized(Support.get_user_support, user_email)
                if not result:
                    return False

            return True
        except Exception as ex:
            logging.exception(ex)
        return False
