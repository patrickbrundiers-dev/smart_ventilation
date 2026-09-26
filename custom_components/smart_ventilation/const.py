DOMAIN = "smart_ventilation"

CONF_NAME = "name"
CONF_VOLUME = "volume"
CONF_WINDOW_DIRECTION = "window_direction"
CONF_INDOOR_HUMIDITY = "indoor_absolute_humidity"
CONF_OUTDOOR_HUMIDITY = "outdoor_absolute_humidity"
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

# Jahreszeit-Modus
CONF_SEASON_MODE = "season_mode"
CONF_SEASON_THRESHOLD = "season_threshold"
SEASON_AUTO = "auto"
SEASON_SUMMER = "summer"
SEASON_WINTER = "winter"
DEFAULT_SEASON_MODE = SEASON_AUTO
DEFAULT_SEASON_THRESHOLD = 15.0  # °C – Heizgrenztemperatur
SEASON_HYSTERESIS = 1.0  # °C – verhindert ständiges Hin- und Herspringen

# Benachrichtigungen: Liste von notify-Diensten (ersetzt das alte Textfeld)
CONF_NOTIFY_SERVICES = "notify_services"

# Bester Lüftungszeitpunkt (Wettervorhersage)
CONF_WEATHER = "weather_entity"
FORECAST_REFRESH_MINUTES = 30
FORECAST_RETRY_MINUTES = 5
FORECAST_HOURS = 24
FORECAST_DAY_START = 7   # keine Empfehlungen vor 7 Uhr ...
FORECAST_DAY_END = 22    # ... und nicht ab 22 Uhr
FORECAST_MIN_GAIN = 1.0  # g/m³ – darunter lohnt sich Lüften kaum
FORECAST_MAX_RAIN_MM = 0.2
FORECAST_MAX_RAIN_PROB = 50
