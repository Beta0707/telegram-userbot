#!/bin/bash
set -e

echo "🚀 Instalando Telegram Userbot en Oracle Cloud..."

# Actualizar sistema
echo "📦 Actualizando sistema..."
sudo apt-get update
sudo apt-get install -y python3.11 python3.11-venv git

# Clonar repo
echo "📥 Clonando repositorio..."
cd /home/ubuntu
git clone https://github.com/Beta0707/telegram-userbot
cd telegram-userbot

# Virtual env
echo "🐍 Creando virtual environment..."
python3.11 -m venv venv
source venv/bin/activate

# Instalar dependencias
echo "📚 Instalando dependencias..."
pip install --upgrade pip
pip install -r requirements.txt

# Crear .env
echo "📝 Creando archivo .env..."
cat > .env << 'EOF'
# Telegram API
TELEGRAM_API_ID=
TELEGRAM_API_HASH=
TELEGRAM_PHONE_1=
TELEGRAM_PHONE_2=
TELEGRAM_PHONE_3=

# Anthropic
ANTHROPIC_API_KEY=

# Bot config
RECEPTOR_USER_ID=
GROUP_MEDIA_ID=
GROUP_LINK=

# Broadcast
BROADCAST_COOLDOWN_MINUTES=5
BROADCAST_WAIT_HOURS=4
ACCOUNT_OFFSET_MINUTES_1=0
ACCOUNT_OFFSET_MINUTES_2=90
ACCOUNT_OFFSET_MINUTES_3=180
EOF

echo "✅ Setup completado!"
echo ""
echo "📋 Próximos pasos:"
echo "1. Edita el archivo .env con tus credenciales:"
echo "   nano /home/ubuntu/telegram-userbot/.env"
echo ""
echo "2. Ejecuta el bot:"
echo "   cd /home/ubuntu/telegram-userbot"
echo "   source venv/bin/activate"
echo "   nohup python main.py > bot.log 2>&1 &"
echo ""
echo "3. Ver logs:"
echo "   tail -f /home/ubuntu/telegram-userbot/bot.log"
