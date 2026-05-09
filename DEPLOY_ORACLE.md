# Deploy en Oracle Cloud (Gratis)

## 1. Crear cuenta
- Ve a: https://www.oracle.com/cloud/free/
- Crea cuenta gratis (sin tarjeta requerida para siempre)

## 2. Crear VM
- **Compute → Instances → Create Instance**
- **Image:** Ubuntu 22.04 (siempre gratis)
- **Shape:** Ampere (ARM, gratis)
- Descarga tu SSH key

## 3. Conectar a la VM
```bash
ssh -i tu-ssh-key.key ubuntu@IP_DE_LA_VM
```

## 4. Instalar dependencias
```bash
sudo apt update
sudo apt install -y python3.11 git
```

## 5. Clonar y ejecutar el bot
```bash
git clone https://github.com/Beta0707/telegram-userbot
cd telegram-userbot

# Crear virtual env
python3.11 -m venv venv
source venv/bin/activate

# Instalar
pip install -r requirements.txt

# Crear .env con tus credenciales
nano .env
# (pega tus variables)

# Ejecutar
nohup python main.py > bot.log 2>&1 &

# Ver logs en tiempo real
tail -f bot.log
```

## 6. Listo
✅ Bot corriendo 24/7 de forma gratuita
