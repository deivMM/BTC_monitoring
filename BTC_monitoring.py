import os
import time
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText

import requests
from dotenv import load_dotenv

load_dotenv()

# ---- Config ----
CURRENCY = "eur"
THRESHOLD_PCT = 5.0          # % de cambio respecto a la media de ayer que dispara la alerta
CHECK_INTERVAL_SECONDS = 60  # cada cuánto se comprueba el precio

DAILY_REPORT_HOUR = 21       # hora (0-23) a la que se envía el email diario con el resumen
DAILY_REPORT_MINUTE = 0      # minuto (0-59) a la que se envía el email diario con el resumen

MAX_ALERTS_PER_DAY = 1       # nº máximo de emails de alerta por umbral que se envían al día

EMAIL_USER = os.environ["EMAIL_USER"]
EMAIL_PASS = os.environ["EMAIL_PASS"]


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

    return sum(yesterday_prices) / len(yesterday_prices)


# ---- Email ----
def send_email(subject, body):
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_USER
    msg["To"] = EMAIL_USER  # te lo envías a ti mismo

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)

    print(f"Correo enviado: {subject}")


# ---- Lógica de comprobación / alerta ----
def check_price(current_price, yesterday_avg, threshold_pct):
    pct_change = (current_price - yesterday_avg) / yesterday_avg * 100

    if pct_change > threshold_pct:
        direction = "SUBIDA"
    elif pct_change < -threshold_pct:
        direction = "BAJADA"
    else:
        direction = None

    status = (
        f"BTC {pct_change:+.2f}% vs media de ayer "
        f"(ahora €{current_price:,.2f}, media ayer €{yesterday_avg:,.2f})"
    )
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {status}")

    return direction, pct_change, status


def main():
    print(
        f"Iniciando monitor de BTC — umbral ±{THRESHOLD_PCT}%, "
        f"comprobando cada {CHECK_INTERVAL_SECONDS}s, "
        f"resumen diario a las {DAILY_REPORT_HOUR:02d}:{DAILY_REPORT_MINUTE:02d}\n"
    )

    yesterday_avg = get_yesterday_average_price()
    print(f"Media de ayer: €{yesterday_avg:,.2f}\n")

    last_avg_fetch_date = datetime.now(timezone.utc).date()
    last_alert_date = None
    alerts_sent_today = 0
    last_daily_report_date = None

    while True:
        try:
            now_utc = datetime.now(timezone.utc)

            # Recalcular la media de ayer una vez al día (al cruzar de día)
            if now_utc.date() != last_avg_fetch_date:
                yesterday_avg = get_yesterday_average_price()
                last_avg_fetch_date = now_utc.date()
                print(f"Media de ayer actualizada: €{yesterday_avg:,.2f}")

            current_price = get_current_price()
            direction, pct_change, status = check_price(current_price, yesterday_avg, THRESHOLD_PCT)

            # --- Alerta por umbral superado ---
            local_now = datetime.now()

            # Reiniciar el contador de alertas al cambiar de día
            if last_alert_date != local_now.date():
                last_alert_date = local_now.date()
                alerts_sent_today = 0

            if direction and alerts_sent_today < MAX_ALERTS_PER_DAY:
                emoji = "🔺" if direction == "SUBIDA" else "🔻"
                send_email(
                    subject=f"{emoji} Alerta BTC: {direction} {pct_change:+.2f}%",
                    body=status,
                )
                alerts_sent_today += 1

            # --- Resumen diario a la hora configurada ---
            if (
                local_now.hour == DAILY_REPORT_HOUR
                and local_now.minute == DAILY_REPORT_MINUTE
                and local_now.date() != last_daily_report_date
            ):
                send_email(
                    subject="📊 Resumen diario BTC",
                    body=(
                        f"Precio actual ({local_now.strftime('%H:%M')}): €{current_price:,.2f}\n"
                        f"Media del día anterior: €{yesterday_avg:,.2f}\n"
                        f"Variación: {pct_change:+.2f}%"
                    ),
                )
                last_daily_report_date = local_now.date()

        except requests.RequestException as e:
            print(f"Fallo de conexión: {e}")
        except ValueError as e:
            print(f"Error de datos: {e}")

        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()