# 🚀 GUÍA RÁPIDA DE INICIO

## 1️⃣ CONFIGURAR CREDENCIALES

Copia `.env.example` a `.env` y actualiza con tus valores:

```bash
cp .env.example .env
nano .env
```

Necesitas:
- `TELEGRAM_API_ID` → De https://my.telegram.org
- `TELEGRAM_API_HASH` → De https://my.telegram.org  
- `TELEGRAM_PHONE` → Tu número Telegram (+549...)
- `ANTHROPIC_API_KEY` → De https://console.anthropic.com

## 2️⃣ INSTALAR DEPENDENCIAS

```bash
pip install -r requirements.txt
```

## 3️⃣ ACTUALIZAR PRECIOS (IMPORTANTE)

Edita `config.json`:
- Busca `"TU_NOMBRE_AQUI"` → Reemplaza con tu nombre
- Busca números de cuenta/CBU → Reemplaza con los tuyos
- Guarda el archivo

## 4️⃣ EJECUTAR EL BOT

```bash
python main.py
```

Deberías ver:
```
✅ Conectado como: Tu Nombre
👂 Escuchando mensajes privados...
```

## 5️⃣ PROBAR

1. Abre Telegram en otra cuenta
2. Envía mensaje privado a tu userbot
3. Recibe respuesta automática en 2-3 segundos ✅

---

## ¿QUÉ HACE EL BOT?

- ✅ Responde automáticamente a mensajes privados
- ✅ Detecta país del usuario (Argentina, México, Brasil, etc)
- ✅ Muestra precios en moneda LOCAL
- ✅ Muestra métodos de pago LOCALES
- ✅ Guarda todo en base de datos
- ✅ Usa IA (Claude) para respuestas naturales

## 📁 ARCHIVOS

- `main.py` → Bot principal
- `database_completa.py` → Gestor de base de datos
- `config.json` → Precios y métodos de pago (ACTUALIZA ESTO)
- `.env` → Credenciales (GUARDIA SECRETO)
- `requirements.txt` → Dependencias
- `logs/` → Archivos de log
- `userbot_completo.db` → Base de datos (se crea automáticamente)

## 🆘 SI ALGO FALLA

```bash
# Ver logs
tail -f logs/userbot.log

# Reinstalar si hay error
pip install --upgrade -r requirements.txt

# Resetear sesión si no conecta
rm userbot_session.session
python main.py
```

---

**¡Listo para recibir clientes automáticamente! 🎉**
