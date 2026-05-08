# 🚀 SETUP: Userbot Multi-Cuenta (3 Cuentas)

## ¿QUÉ CAMBIÓ?

El userbot ahora soporta **3 cuentas simultáneas** que responden mensajes en paralelo con IA profesional. Cada imagen que reciban los clientes se reenvía automáticamente a tu cuenta receptora.

### Nuevos Archivos
- `prompt_vendedor.py` — Sistema de vendedor profesional "Alex" (nunca regala, siempre vende)
- `handlers.py` — Manejadores de mensajes de texto y media
- `accounts.py` — Gestor de conexiones multi-cuenta

### Archivos Modificados
- `main.py` — Completamente reescrito para arquitectura multi-cuenta
- `database_completa.py` — WAL mode + timeout=30 para escrituras concurrentes
- `.env.example` — Variables para 3 cuentas + receptor

---

## 📋 PASOS PREVIOS (UNA SOLA VEZ)

### 1️⃣ Obtén tus valores de Telegram

Ve a **https://my.telegram.org/apps** y anota:
- **API_ID** → número (ej: 31767362)
- **API_HASH** → cadena de 32 caracteres

Estos valores son **IGUALES para las 3 cuentas**.

### 2️⃣ Obtén el USER ID de la cuenta receptora

En Telegram, abre una conversación privada con **@userinfobot** y presiona START.
Te mostrará tu `Id: 123456789` — anota ese número.

### 3️⃣ Configura el .env

Copia `.env.example` a `.env` y actualiza:

```bash
cp .env.example .env
nano .env
```

Reemplaza:
- `TELEGRAM_API_ID` → tu API_ID
- `TELEGRAM_API_HASH` → tu API_HASH
- `TELEGRAM_PHONE_1/2/3` → tus 3 números de teléfono (+5491112345678)
- `ANTHROPIC_API_KEY` → tu clave de Claude (https://console.anthropic.com)
- `RECEPTOR_USER_ID` → tu User ID numerico

Ejemplo completo:
```
TELEGRAM_API_ID=31767362
TELEGRAM_API_HASH=abc123...
TELEGRAM_PHONE_1=+5491123456789
TELEGRAM_PHONE_2=+5491187654321
TELEGRAM_PHONE_3=+5491134567890
ANTHROPIC_API_KEY=sk-ant-api03-xyz...
RECEPTOR_USER_ID=987654321
```

---

## 🔐 AUTENTICACIÓN (PRIMERA VEZ - INTERACTIVO)

Las sesiones se crean **de una en una**. Telethon pedirá el código SMS por terminal.

### Crear Sesión 1
```bash
# .env con SOLO cuenta 1 activa (PHONE_2 y PHONE_3 vacíos)
TELEGRAM_PHONE_1=+5491123456789
TELEGRAM_PHONE_2=
TELEGRAM_PHONE_3=

python main.py
# Telethon pide código SMS → ingresa el código que recibiste por SMS
# Se crea automáticamente: session_cuenta1.session
# Presiona Ctrl+C para parar
```

### Crear Sesión 2
```bash
# Actualizar .env con PHONE_2
TELEGRAM_PHONE_2=+5491187654321

python main.py
# Ingresa código SMS para cuenta 2
# Se crea: session_cuenta2.session
# Ctrl+C
```

### Crear Sesión 3
```bash
# Actualizar .env con PHONE_3
TELEGRAM_PHONE_3=+5491134567890

python main.py
# Ingresa código SMS para cuenta 3
# Se crea: session_cuenta3.session
# Ctrl+C
```

### Activar las 3 (¡SIN CÓDIGOS!)
```bash
# .env ya tiene las 3 configuradas
# Ahora las sesiones existen, NO pide códigos SMS
python main.py

# Verás:
# ✅ [session_cuenta1] Conectado como: Tu Nombre 1
# ✅ [session_cuenta2] Conectado como: Tu Nombre 2
# ✅ [session_cuenta3] Conectado como: Tu Nombre 3
# 👂 Escuchando mensajes privados...
```

---

## 🎯 FLUJO DE OPERACIÓN

### Cliente envía **TEXTO**
```
Cliente → Mensaje de texto (ej: "Hola, quiero datos")
              ↓
Bot (Alex) → Respuesta inteligente con precios/métodos de pago
              ↓
Base de datos → Se guarda la conversación con nombre de sesión
```

### Cliente envía **IMAGEN** (comprobante de pago)
```
Cliente → Imagen/foto
              ↓
Bot → Reenvía la imagen a tu RECEPTOR_USER_ID
              ↓
Bot → Responde al cliente: "Recibimos tu comprobante..."
              ↓
Tú (receptor) → Ves la imagen con nombre del cliente e ID de sesión
                → Verificas el comprobante
                → Le entregas el grupo con el contenido
```

---

## ⚙️ CARACTERÍSTICAS DEL PROMPT "ALEX"

- **Profesional:** No se presenta como bot, responde como un asesor humano
- **Vendedor:** Nunca regala nada, siempre cierra la venta
- **Inteligente:** Detecta país → Muestra precios en moneda local + métodos de pago del país
- **Maneja objeciones:** Si dicen "es caro", responde con valor vs costo
- **Brevedad:** Máx 3-4 oraciones por respuesta (natural en Telegram)

### Ejemplos de respuestas:
```
Cliente: "Es muy caro"
Alex: "Lo entiendo. Pero calcula cuanto te costaria conseguir esos contactos 
      uno por uno. Este es el mejor precio del mercado. Cual paquete te interesa?"

Cliente: "Voy a pensarlo"
Alex: "Perfecto, tomalo con calma. Solo te aviso que el precio puede cambiar 
      esta semana, asi que si te interesa avisame hoy."
```

---

## 📊 BASE DE DATOS

La tabla `conversaciones` ahora tiene una columna `cuenta_sesion` que registra:
- `session_cuenta1`, `session_cuenta2` o `session_cuenta3`

Útil para auditoría: puedes ver desde qué cuenta cada cliente fue atendido.

### Ver estadísticas
El bot imprime estadísticas cada 10 minutos en los logs:
```
📊 Total usuarios: 42
🌍 Países activos: 5
📦 Órdenes: 12
✅ Pagadas: 8
💰 Ventas: $184.50
```

---

## 🆘 SI ALGO FALLA

### Error: "Faltan credenciales"
Verifica que tu `.env` tenga PHONE_1, PHONE_2, PHONE_3, ANTHROPIC_KEY y RECEPTOR_USER_ID

### Error: "database is locked"
Esperado en transiciones. WAL mode maneja esto. Si persiste:
```bash
rm *.session-wal *.session-shm
```

### Cliente no recibe respuesta
- Verifica logs: `tail -f logs/userbot.log`
- ¿El cliente escribió a un grupo? Bot solo responde privados
- ¿Está rate limited? Max 5 mensajes/minuto

### Imágenes no se reenvían
- Verifica que RECEPTOR_USER_ID es correcto
- Importante: desde cada cuenta, envía UN MENSAJE MANUAL al receptor primero (así Telegram lo permite)

---

## 🔄 ACTUALIZAR PRECIOS

Edita `config.json`:
- Busca "precios_descuento" por país
- Actualiza los montos
- Guarda
- Reinicia el bot

El bot cargará los precios en la BD al arrancar (log: "📊 Cargando precios en BD...")

---

## 📈 MONITOREO

### Ver logs en tiempo real
```bash
tail -f logs/userbot.log
```

### Ver qué pasa por sesión
Los logs muestran `[session_cuenta1]`, `[session_cuenta2]`, etc en cada línea.

### Ver conversaciones guardadas
```bash
# Conéctate a la BD (si tienes sqlite3)
sqlite3 userbot_completo.db
SELECT usuario_id, mensaje_usuario, respuesta_bot, cuenta_sesion, timestamp 
FROM conversaciones 
ORDER BY timestamp DESC LIMIT 10;
```

---

## ✅ CHECKLIST ANTES DE PRODUCCIÓN

- [ ] Las 3 sesiones creadas (session_cuenta1/2/3.session existen)
- [ ] `.env` con valores reales (no placeholders)
- [ ] Prueba: envía mensaje privado a cada cuenta desde otra cuenta
- [ ] Las 3 responden con IA en 2-3 segundos
- [ ] Prueba: envía foto a una cuenta
- [ ] Recibes la foto en tu RECEPTOR_USER_ID
- [ ] Verifica que el cliente vea: "Recibimos tu comprobante..."
- [ ] Revisa logs para ver `[session_cuenta1]`, `[session_cuenta2]`, `[session_cuenta3]`

---

## 🎉 ¡LISTO!

Tu userbot multi-cuenta está operativo. Todas las 3 cuentas responden con IA profesional, manejan 12+ países con precios locales, y reenvían comprobantes automáticamente.

**Próximos pasos:**
1. Actualiza nombres/datos de pago en `config.json`
2. Agrega las 3 cuentas a tus promociones
3. Monitorea logs durante las primeras horas
4. Ajusta el prompt en `prompt_vendedor.py` si necesita personalizaciones

¡A vender! 💪
