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
START_DIFF = 1.0      # g/m³ – erst ab diesem Unterschied lohnt sich Lüften gegen Feuchte
HUMID_RH = 65.0       # % rel. Feuchte innen – ab hier immer „zu feucht“
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

# Mehrere Fenster, Warnungen, Ruhezeiten, Heizung
CONF_COOL_LIMIT = "cool_limit"
DEFAULT_COOL_LIMIT = 18.0          # °C, 0 = aus
WINTER_OVERTIME_MINUTES = 5        # Warnung, wenn Winter-Höchstdauer um so viel überschritten
CONF_QUIET_START = "quiet_start"
CONF_QUIET_END = "quiet_end"
DEFAULT_QUIET_START = "22:00:00"
DEFAULT_QUIET_END = "07:00:00"
SNOOZE_MINUTES = 30
ACTION_SNOOZE = "SV_SNOOZE_"
ACTION_SKIP = "SV_SKIP_"
CONF_CLIMATES = "climate_entities"
HEATING_DELAY_SECONDS = 60         # erst nach 1 Min. offen Heizung absenken
ON_STATES = ("on", "open", "true", "1")
OFF_STATES = ("off", "closed", "false", "0")
TARGET_PROGRESS = 0.7              # Ziel auch erreicht, wenn 70 % des Feuchteunterschieds abgebaut
TARGET_MIN_SECONDS = 60            # frühestens nach 1 Min. "Ziel erreicht"
POST_VENT_PAUSE_MINUTES = 60       # nach dem Lüften 1 h keine neue Erinnerung

# Schimmelrisiko an der Wand (DIN 4108-2: 80 % rel. Feuchte an der Oberfläche)
CONF_BUILDING = "building_standard"
DEFAULT_BUILDING = "average"
U_VALUES = {           # W/(m²K) Außenwand
    "old": 1.4,        # Altbau ungedämmt
    "average": 1.0,    # 60er–90er Jahre
    "insulated": 0.35, # gedämmt / ab ca. 2000
    "passive": 0.15,   # Neubau / Passivhaus
}
RSI_CORNER = 0.35      # m²K/W – Außenecke / hinter Möbeln (ungünstigste Stelle)
MOLD_RH_HIGH = 80.0
MOLD_RH_ELEVATED = 70.0

# CO₂ (optional)
CONF_CO2 = "co2_sensor"
CO2_OUTDOOR = 420
CO2_TARGET = 800
CO2_ELEVATED = 1000
CO2_HIGH = 1400

# Wärmeverlust / Kosten
CONF_ENERGY_PRICE = "energy_price"
DEFAULT_ENERGY_PRICE = 0.12            # €/kWh
AIR_HEAT_CAPACITY_WH = 0.34            # Wh/(m³·K)

# Anwesenheit & Übersicht
CONF_PERSONS = "persons"
CONF_ENTRY_TYPE = "entry_type"
ENTRY_TYPE_ROOM = "room"
ENTRY_TYPE_OVERVIEW = "overview"
CONF_COMBINE = "combine_notifications"
VERSION = "2.3.8"
ISSUE_AFTER_MINUTES = 10  # Reparatur-Hinweis, wenn ein Sensor so lange ausfällt

# Bad-Modus
CONF_SHOWER = "shower_sensor"
CONF_SHOWER_DETECT = "shower_detect"
SHOWER_JUMP = 1.5                 # g/m³ Anstieg in ...
SHOWER_WINDOW_MINUTES = 10        # ... so vielen Minuten = Duschen erkannt
SHOWER_FOLLOWUP_MINUTES = 30      # danach nachfassen, wenn noch feucht

# Urlaub
CONF_VACATION = "vacation_entity"
CONF_VACATION_KEYWORD = "vacation_keyword"

# Sommer: Kühlen per Lüften
CONF_COMFORT_TEMP = "comfort_temperature"
DEFAULT_COMFORT_TEMP = 23.0
COOL_MIN_DIFF = 2.0               # draußen mind. 2 °C kühler
COOL_MAX_EXTRA_HUMIDITY = 1.0     # g/m³ – nicht kühlen, wenn draußen viel feuchter

# Luftentfeuchter
CONF_DEHUMIDIFIER = "dehumidifier_entity"
DEHUM_ON_RH = 60.0
DEHUM_OFF_RH = 55.0
DEHUM_MIN_RUNTIME_MINUTES = 15

# Wochenbericht
CONF_WEEKLY_REPORT = "weekly_report"
REPORT_WEEKDAY = 6                # Sonntag
REPORT_HOUR = 19

# Verlauf
TRACE_MAX_POINTS = 240            # 2 h bei 30 s
TRACE_CARD_POINTS = 60

# Schimmel-Frühwarnung über mehrere Tage
MOLD_CRITICAL_MINUTES = 360       # ≥ 6 h Wandfeuchte ≥ 80 % = kritischer Tag
MOLD_STREAK_WARN = 3              # Warnung ab 3 kritischen Tagen in Folge
MOLD_REWARN_DAYS = 7              # bei anhaltender Lage erneut nach einer Woche
MOLD_LOG_DAYS = 62

# Monats-/Jahresvergleich
CONF_MONTHLY_REPORT = "monthly_report"
MONTHLY_REPORT_HOUR = 9           # am 1. des Monats ab 9 Uhr
HISTORY_MONTHS = 36
