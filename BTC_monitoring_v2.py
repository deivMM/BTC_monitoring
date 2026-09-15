import logging
import os
import time
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from logging.handlers import RotatingFileHandler
import smtplib

import requests
from dotenv import load_dotenv

load_dotenv()

# ---- Config ----
CURRENCY = "eur"
THRESHOLD_PCT = 2.0         # % de cambio respecto al valor de referencia que dispara la alerta
CHECK_INTERVAL_SECONDS = 60  # cada cuánto se comprueba el precio
RETRY_WAIT_SECONDS = 30      # espera antes de reintentar tras un fallo al arrancar

# Rutas ancladas al directorio del propio script: si se lanza como servicio
# (systemd, cron, etc.) el directorio de trabajo puede ser otro distinto,
# y así el log siempre queda junto al script pase lo que pase.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(SCRIPT_DIR, "btc_monitor.log")
LOG_MAX_BYTES = 2_000_000    # ~2 MB por archivo
LOG_BACKUP_COUNT = 5         # guarda hasta 5 archivos rotados (~12 MB en total)

EMAIL_USER = os.environ["EMAIL_USER"]
EMAIL_PASS = os.environ["EMAIL_PASS"]

# Lista de destinatarios de las alertas.
# En el .env: EMAIL_TO="persona1@gmail.com,persona2@gmail.com,persona3@gmail.com"
# Si no se define EMAIL_TO, se envía solo a EMAIL_USER.
EMAIL_TO = [
    email.strip()
    for email in os.environ.get("EMAIL_TO", EMAIL_USER).split(",")
    if email.strip()
]


# ---- Logging ----
# En vez de print(), se usa logging: escribe a consola (si la hay) y a un
# archivo con rotación, para que corriendo semanas no crezca sin límite.
logger = logging.getLogger("btc_monitor")
logger.setLevel(logging.INFO)

_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

_file_handler = RotatingFileHandler(
    LOG_FILE, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT, encoding="utf-8"
)
_file_handler.setFormatter(_formatter)
logger.addHandler(_file_handler)

_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_formatter)
logger.addHandler(_console_handler)


# ---- Datos de precio ----
def get_current_price():
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": "bitcoin", "vs_currencies": CURRENCY}
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    return response.json()["bitcoin"][CURRENCY]


def get_yesterday_average_price():
    """
    Descarga precios horarios de los últimos 2 días y promedia los puntos
    que caen dentro de la fecha de ayer (UTC).
    Devuelve (media, fecha_de_ayer).
    """
    url = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"
    params = {"vs_currency": CURRENCY, "days": 2}
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()

    now = datetime.now(timezone.utc)
    yesterday_date = (now - timedelta(days=1)).date()

    yesterday_prices = [
        price
        for timestamp_ms, price in data["prices"]
        if datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).date() == yesterday_date
    ]

    if not yesterday_prices:
        raise ValueError("No se han encontrado datos de precio para ayer.")

    return sum(yesterday_prices) / len(yesterday_prices), yesterday_date


def get_yesterday_average_price_with_retry():
    """Reintenta indefinidamente al arrancar si no hay red todavía."""
    while True:
        try:
            return get_yesterday_average_price()
        except (requests.RequestException, ValueError) as e:
            logger.warning(f"No se pudo obtener la media de ayer ({e}). Reintentando en {RETRY_WAIT_SECONDS}s...")
            time.sleep(RETRY_WAIT_SECONDS)


# ---- Email ----
def send_email(subject, body):
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_USER
    msg["To"] = ", ".join(EMAIL_TO)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)

    logger.info(f"Correo enviado a {', '.join(EMAIL_TO)}: {subject}")


# ---- Lógica de comprobación / alerta ----
def check_price(current_price, reference_price, reference_description, threshold_pct):
    pct_change = (current_price - reference_price) / reference_price * 100

    if pct_change > threshold_pct:
        direction = "SUBIDA"
    elif pct_change < -threshold_pct:
        direction = "BAJADA"
    else:
        direction = None

    status = (
        f"BTC {pct_change:+.2f}% vs referencia\n"
        f"Ahora: €{current_price:,.2f}\n"
        f"Referencia: €{reference_price:,.2f} ({reference_description})"
    )
    logger.info(
        f"BTC {pct_change:+.2f}% | ahora €{current_price:,.2f} | "
        f"referencia €{reference_price:,.2f} ({reference_description})"
    )

    return direction, pct_change, status


def main():
    logger.info(
        f"Iniciando monitor de BTC — umbral ±{THRESHOLD_PCT}%, "
        f"comprobando cada {CHECK_INTERVAL_SECONDS}s, "
        f"destinatarios: {', '.join(EMAIL_TO)}"
    )

    # Valor de referencia inicial: media del día anterior.
    reference_price, yesterday_date = get_yesterday_average_price_with_retry()
    reference_description = f"media del día anterior, {yesterday_date.isoformat()}"
    logger.info(f"Referencia inicial: €{reference_price:,.2f} ({reference_description})")

    while True:
        try:
            current_price = get_current_price()
            direction, pct_change, status = check_price(
                current_price, reference_price, reference_description, THRESHOLD_PCT
            )

            # Esta primera comprobación (justo tras arrancar) ya puede disparar
            # un aviso si el precio actual está fuera de rango respecto a la
            # media de ayer, tal y como se pedía.
            if direction:
                emoji = "🔺" if direction == "SUBIDA" else "🔻"
                send_email(
                    subject=f"{emoji} Alerta BTC: {direction} {pct_change:+.2f}%",
                    body=status,
                )
                # A partir de ahora la referencia pasa a ser el precio que ha
                # disparado la alerta, con la fecha y hora exactas en las que
                # se registró. No se volverá a avisar hasta que el precio se
                # mueva de nuevo ±THRESHOLD_PCT respecto a este nuevo valor,
                # y así sucesivamente.
                reference_price = current_price
                reference_description = f"precio registrado el {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                logger.info(f"Nueva referencia: €{reference_price:,.2f} ({reference_description})")

        except requests.RequestException as e:
            logger.warning(f"Fallo de conexión: {e}")
        except ValueError as e:
            logger.warning(f"Error de datos: {e}")
        except Exception:
            # Cualquier otro fallo inesperado se registra con su traceback
            # pero no debe tumbar un proceso pensado para correr semanas.
            logger.exception("Error inesperado en el bucle principal")

        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()