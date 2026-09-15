import os
from dotenv import load_dotenv
import smtplib
from email.mime.text import MIMEText

load_dotenv()

email_user = os.environ["EMAIL_USER"]
email_pass = os.environ["EMAIL_PASS"]

msg = MIMEText("¡Ha habido un cambio en la página que monitorizas!")

msg["Subject"] = "Alerta de monitorización"
msg["From"] = email_user
msg["To"] = email_user  # te lo envías a ti mismo

with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
    server.login(email_user, email_pass)
    server.send_message(msg)

print("Correo enviado")
