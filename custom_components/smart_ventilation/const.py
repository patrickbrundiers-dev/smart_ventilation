DOMAIN = "smart_ventilation"

CONF_NAME = "name"
CONF_VOLUME = "volume"
DEFAULT_VOLUME = 40.0  # m³ – typisches Schlafzimmer, falls beim Einrichten nichts angegeben wurde
CONF_WINDOW_DIRECTION = "window_direction"
CONF_INDOOR_HUMIDITY = "indoor_absolute_humidity"
CONF_OUTDOOR_HUMIDITY = "outdoor_absolute_humidity"
# Optional: echter %-Sensor statt der aus AH+Temperatur zurückgerechneten rel. Feuchte (indoor_rh/
# outdoor_rh in coordinator.py) - vermeidet die doppelte Umrechnung, wenn ohnehin ein physischer
# RH-Sensor vorhanden ist. Betrifft NUR indoor_rh/outdoor_rh (Raumluft/Außenluft bei Lufttemperatur);
# wall_rh (Schimmelrisiko an der kalten Wand) bleibt bewusst über AH+Wandtemperatur berechnet, das
# kann kein Sensor direkt messen.
CONF_INDOOR_RH = "indoor_relative_humidity"
CONF_OUTDOOR_RH = "outdoor_relative_humidity"
CONF_INDOOR_TEMP = "indoor_temperature"
CONF_OUTDOOR_TEMP = "outdoor_temperature"
CONF_WIND_SPEED = "wind_speed"
CONF_WIND_DIRECTION = "wind_direction"
CONF_WIND_IS_FROM = "wind_is_from"
CONF_RAIN = "rain"
CONF_WINDOW = "window"
CONF_MAX_TEMP_DIFF = "max_temperature_difference"
CONF_USE_SUN = "use_sun"
CONF_MIN_SUN_ELEVATION = "min_sun_elevation"
CONF_SUN_ENTITY = "sun_entity"
CONF_NOTIFY_SERVICE = "notify_service"
CONF_NOTIFICATION_COOLDOWN = "notification_cooldown"

DEFAULT_START_DIFF = 0.7
DEFAULT_TARGET_DIFF = 0.5
START_DIFF = 1.0      # g/m³ – erst ab diesem Unterschied lohnt sich Lüften gegen Feuchte
HUMID_RH = 65.0       # % rel. Feuchte innen – ab hier immer „zu feucht“
CONF_HUMID_HYSTERESIS = "humidity_hysteresis"
DEFAULT_HUMID_HYSTERESIS = 0.1       # g/m³ – Puffer, bevor eine aktive Feuchte-Empfehlung wieder ausgeht
HUMID_RH_HYSTERESIS_RATIO = 30.0     # rel.-Feuchte-Puffer = g/m³-Puffer × dieser Faktor (0,1 -> 3,0 Punkte)
DEFAULT_MIN_SESSION = 120
DEFAULT_MAX_SESSION = 7200
DEFAULT_MAX_TEMP_DIFF = 3.0  # Sommer: nicht lüften, wenn draußen so viel wärmer
DEFAULT_MIN_SUN_ELEVATION = 15.0
DEFAULT_SUN_ENTITY = "sun.sun"
DEFAULT_NOTIFICATION_COOLDOWN = 180  # Minuten
MIN_FINAL_DIFF = 0.1  # Untergrenze, wenn bis unter Außenniveau gelüftet wurde

STORE_VERSION = 1
STORE_KEY = "smart_ventilation_learning"

CONF_TARGET_ABS = "target_absolute_humidity"
DEFAULT_TARGET_ABS = 11.5  # g/m³ – Tagesziel absolute Feuchte innen

# Raumtyp: liefert beim Einrichten nur einen Vorschlag für das Tagesziel (Feld bleibt frei
# änderbar) – überschreibt einen bewusst abweichend eingetragenen Wert nicht.
CONF_ROOM_TYPE = "room_type"
ROOM_TYPE_BEDROOM = "bedroom"
ROOM_TYPE_BATHROOM = "bathroom"
ROOM_TYPE_LIVING = "living"
ROOM_TYPE_KITCHEN = "kitchen"
ROOM_TYPE_OTHER = "other"
DEFAULT_ROOM_TYPE = ROOM_TYPE_OTHER
ROOM_TYPE_TARGET_ABS = {
    ROOM_TYPE_BEDROOM: 8.5,
    ROOM_TYPE_BATHROOM: 11.5,
    ROOM_TYPE_LIVING: 10.0,
    ROOM_TYPE_KITCHEN: 10.5,
    ROOM_TYPE_OTHER: DEFAULT_TARGET_ABS,
}

# Jahreszeit-Modus
CONF_SEASON_MODE = "season_mode"
CONF_SEASON_THRESHOLD = "season_threshold"
SEASON_AUTO = "auto"
SEASON_SUMMER = "summer"
SEASON_WINTER = "winter"
DEFAULT_SEASON_MODE = SEASON_AUTO
DEFAULT_SEASON_THRESHOLD = 15.0
SEASON_HYSTERESIS = 1.0
SEASON_CONFIRM_HOURS = 6
SEASON_FORECAST_DAYS = 3
SEASON_FIXED_WINTER_MONTHS = (12, 1, 2)
SEASON_FIXED_SUMMER_MONTHS = (6, 7, 8)

# Benachrichtigungen
CONF_NOTIFY_SERVICES = "notify_services"

# Bester Lüftungszeitpunkt
CONF_WEATHER = "weather_entity"
FORECAST_REFRESH_MINUTES = 30
FORECAST_RETRY_MINUTES = 5
FORECAST_HOURS = 24
FORECAST_DAY_START = 7
FORECAST_DAY_END = 22
FORECAST_MIN_GAIN = 1.0
FORECAST_MAX_RAIN_MM = 0.2
FORECAST_MAX_RAIN_PROB = 50
MIN_FORECAST_WIND_FACTOR = 0.3
RAIN_SOON_COOLDOWN_MINUTES = 30
RAIN_SOON_URGENCY_BOOST = 2.0

# Party-Modus
PARTY_MODE_HOURS = 3
PARTY_MODE_TARGET_REDUCTION = 1.5
PARTY_MODE_COOLDOWN_MINUTES = 20

# Mehrere Fenster, Warnungen, Ruhezeiten, Heizung
CONF_COOL_LIMIT = "cool_limit"
DEFAULT_COOL_LIMIT = 18.0
WINTER_OVERTIME_MINUTES = 5
CONF_QUIET_START = "quiet_start"
CONF_QUIET_END = "quiet_end"
DEFAULT_QUIET_START = "22:00:00"
DEFAULT_QUIET_END = "07:00:00"
CONF_QUIET_WEEKEND_DIFFERENT = "quiet_weekend_different"
CONF_QUIET_START_WEEKEND = "quiet_start_weekend"
CONF_QUIET_END_WEEKEND = "quiet_end_weekend"
SNOOZE_MINUTES = 30
ACTION_SNOOZE = "SV_SNOOZE_"
ACTION_SKIP = "SV_SKIP_"
CONF_CLIMATES = "climate_entities"
HEATING_DELAY_SECONDS = 60
ON_STATES = ("on", "open", "true", "1")
OFF_STATES = ("off", "closed", "false", "0")
TARGET_PROGRESS = 0.7
TARGET_MIN_SECONDS = 60
POST_VENT_PAUSE_MINUTES = 60
POST_VENT_FORECAST_MAX_HOURS = 4

# Schimmelrisiko
CONF_BUILDING = "building_standard"
DEFAULT_BUILDING = "average"
U_VALUES = {
    "old": 1.4,
    "average": 1.0,
    "insulated": 0.35,
    "passive": 0.15,
}
# Innere Oberflächen-Temperatur nach dem üblichen Wärmeübergangswiderstand Rsi.
# Ein konservatives Minimum für den Temperaturfaktor verhindert unrealistisch
# kalte Wandflächen und damit künstlich erzeugte 100-%-Wandfeuchte.
R_SI = 0.13  # m²K/W
MIN_WALL_SURFACE_TEMPERATURE_FACTOR = 0.70
MOLD_RH_HIGH = 80.0
MOLD_RH_ELEVATED = 70.0
MOLD_RH_WATCH = 65.0
MOLD_RH_CRITICAL = 90.0
MOLD_DEWPOINT_MARGIN_CRITICAL = 0.5
MOLD_TREND_WARN_RH_PER_HOUR = 2.0
MOLD_CURRENT_WARN_MINUTES = 120

# CO₂
CONF_CO2 = "co2_sensor"
CO2_OUTDOOR = 420
CO2_TARGET = 800
CO2_ELEVATED = 1000
CO2_HIGH = 1400

# Wärmeverlust / Kosten
CONF_ENERGY_PRICE = "energy_price"
DEFAULT_ENERGY_PRICE = 0.12
AIR_HEAT_CAPACITY_WH = 0.34

# Anwesenheit & Übersicht
CONF_PERSONS = "persons"
CONF_ENTRY_TYPE = "entry_type"
ENTRY_TYPE_ROOM = "room"
ENTRY_TYPE_OVERVIEW = "overview"
CONF_COMBINE = "combine_notifications"
VERSION = "2.22.12"

# Adaptive decision / learning
ADAPTIVE_SCORE_MIN = 20
ADAPTIVE_SCORE_FULL_OPEN = 62
LEARNING_HISTORY_MAX = 12
GLOBAL_LEARNING_HISTORY_MAX = 24
LEARNING_STALE_DAYS = 45
ISSUE_AFTER_MINUTES = 10

# Bad-Modus
CONF_SHOWER = "shower_sensor"
CONF_SHOWER_DETECT = "shower_detect"
SHOWER_JUMP = 1.5
SHOWER_WINDOW_MINUTES = 10
SHOWER_FOLLOWUP_MINUTES = 30

# Urlaub
CONF_VACATION = "vacation_entity"
CONF_VACATION_KEYWORD = "vacation_keyword"

# Sommer: Kühlen per Lüften
CONF_COMFORT_TEMP = "comfort_temperature"
DEFAULT_COMFORT_TEMP = 23.0
COOL_MIN_DIFF = 2.0
COOL_MAX_EXTRA_HUMIDITY = 1.0

# Vorheizen per Lüften
CONF_PREHEAT_TEMP = "preheat_temperature"
DEFAULT_PREHEAT_TEMP = 19.0
PREHEAT_MIN_WARMER = 2.0
NIGHT_LOW_START_HOUR = 22
NIGHT_LOW_END_HOUR = 9
PREHEAT_RAIN_LOOKAHEAD_HOURS = 2
PREHEAT_MAX_EXTRA_HUMIDITY = 1.0

# Luftentfeuchter
CONF_DEHUMIDIFIER = "dehumidifier_entity"
DEHUM_ON_RH = 60.0
DEHUM_OFF_RH = 55.0
DEHUM_AH_HYSTERESIS = 0.3
DEHUM_RH_HYSTERESIS = 2.0
DEHUM_MIN_RUNTIME_MINUTES = 15
DEHUM_RESTART_COOLDOWN_MINUTES = 10

# Rollo/Jalousie
CONF_SHUTTER = "shutter_entity"
SHUTTER_MIN_RUNTIME_MINUTES = 15

# Zusätzliche optionale Wettersensoren
CONF_SOLAR_RADIATION = "solar_radiation_entity"
SOLAR_RADIATION_MIN = 120.0
CLOUD_COVER_BLOCK = 80.0
CLOUD_COVER_RADIATION_CHECK = 45.0
CLOUD_COVER_RADIATION_MIN = 180.0
CLOUDY_WEATHER_STATES = ("cloudy", "overcast", "rainy", "pouring", "snowy", "snowy-rainy", "fog")
SOLAR_RADIATION_RELEASE = 160.0

CONF_THUNDERSTORM = "thunderstorm_entity"
LOW_RISK_STATES = ("normal", "gering", "kein", "keine", "aus", "nein", "niedrig", "unwahrscheinlich")

CONF_WIND_GUST = "wind_gust_entity"
WIND_GUST_WARN_KMH = 50.0

CONF_FROST = "frost_entity"

# Wochenbericht
CONF_WEEKLY_REPORT = "weekly_report"
REPORT_WEEKDAY = 6
REPORT_HOUR = 19

# Verlauf
TRACE_MAX_POINTS = 240
TRACE_CARD_POINTS = 60

# Schimmel-Frühwarnung
MOLD_CRITICAL_MINUTES = 360
MOLD_STREAK_WARN = 3
MOLD_REWARN_DAYS = 7
MOLD_LOG_DAYS = 62

# Monats-/Jahresvergleich
CONF_MONTHLY_REPORT = "monthly_report"
MONTHLY_REPORT_HOUR = 9

# Tagesarchiv
DAY_LOG_DAYS = 14

# Anomalie-Erkennung
ANOMALY_MIN_MINUTES = 60
ANOMALY_BASELINE_DAYS = 14
ANOMALY_MIN_SAMPLE_DAYS = 5
ANOMALY_FACTOR = 2.5

BUCKET_TRUST_SAMPLES = 5

# Benachrichtigungsziele
CAT_REMINDER = "reminder"
CAT_FINISHED = "finished"
CAT_WARNING = "warning"
CAT_SHOWER = "shower"
CAT_MOLD = "mold"
CAT_WELCOME = "welcome"
CAT_REPORT = "report"
NOTIFY_CATEGORIES = (CAT_REMINDER, CAT_FINISHED, CAT_WARNING, CAT_SHOWER, CAT_MOLD, CAT_WELCOME, CAT_REPORT)

CONF_NOTIFY_TARGETS_REMINDER = "notify_targets_reminder"
CONF_NOTIFY_TARGETS_FINISHED = "notify_targets_finished"
CONF_NOTIFY_TARGETS_WARNING = "notify_targets_warning"
CONF_NOTIFY_TARGETS_SHOWER = "notify_targets_shower"
CONF_NOTIFY_TARGETS_MOLD = "notify_targets_mold"
CONF_NOTIFY_TARGETS_WELCOME = "notify_targets_welcome"
CONF_NOTIFY_TARGETS_REPORT = "notify_targets_report"

CATEGORY_CONF_KEYS = {
    CAT_REMINDER: CONF_NOTIFY_TARGETS_REMINDER,
    CAT_FINISHED: CONF_NOTIFY_TARGETS_FINISHED,
    CAT_WARNING: CONF_NOTIFY_TARGETS_WARNING,
    CAT_SHOWER: CONF_NOTIFY_TARGETS_SHOWER,
    CAT_MOLD: CONF_NOTIFY_TARGETS_MOLD,
    CAT_WELCOME: CONF_NOTIFY_TARGETS_WELCOME,
    CAT_REPORT: CONF_NOTIFY_TARGETS_REPORT,
}
HISTORY_MONTHS = 36
