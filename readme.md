To preview 'readme' file in VS Code -> Press Cmd + Shift + V


python3 -m venv venv
source venv/bin/activate

- Actualizar dependencias con:
pip freeze > requirements.txt

- Instalar dependencias con:
  pip install -r requirements.txt


pip install matplotlib numpy pandas

pip list

deactivate

###########################################################
sudo nano /etc/systemd/system/btc-monitor.service
###########################################################
sudo systemctl daemon-reload
sudo systemctl enable --now btc-monitor


Estado del servicio ---> sudo systemctl status btc-monitor.service

Detener	---> sudo systemctl stop btc-monitor.service
Iniciar ---> manualmente	sudo systemctl start btc-monitor.service
Desactivar del arranque ---> sudo systemctl disable btc-monitor.service
Activar al arranque	---> sudo systemctl enable btc-monitor.service