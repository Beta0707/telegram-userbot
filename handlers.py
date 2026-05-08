"""
Handlers de mensajes para el userbot multi-cuenta.
Maneja mensajes de texto (IA) y media (reenvio de comprobantes de pago).
"""

import logging
from datetime import datetime, timedelta
from telethon import events
from telethon.tl.types import MessageMediaPhoto
from anthropic import Anthropic
from prompt_vendedor import obtener_system_prompt

logger = logging.getLogger(__name__)

MAX_MESSAGES_PER_MINUTE = 5


async def registrar_handler_texto(client, ai_client: Anthropic, db, config: dict,
                                  conversation_history: dict, user_message_times: dict,
                                  nombre_sesion: str):
    """
    Registra el handler de mensajes de texto (IA).
    Responde automáticamente con Claude Anthropic.
    """

    def verificar_rate_limit(user_id: int) -> bool:
        """Verifica si el usuario ha excedido el límite de 5 mensajes por minuto"""
        ahora = datetime.now()
        hace_un_minuto = ahora - timedelta(minutes=1)

        if user_id not in user_message_times:
            user_message_times[user_id] = []

        user_message_times[user_id] = [
            ts for ts in user_message_times[user_id] if ts > hace_un_minuto
        ]

        if len(user_message_times[user_id]) >= MAX_MESSAGES_PER_MINUTE:
            return False

        user_message_times[user_id].append(ahora)
        return True

    async def handle_text_message(event):
        # Ignorar grupos y canales
        if event.is_group or event.is_channel:
            return

        # Ignorar si no tiene texto (eso lo maneja handler_media)
        if not event.message.text:
            return

        # Ignorar si es media (eso lo maneja handler_media)
        if event.message.media:
            return

        user = await event.get_sender()
        user_id = user.id
        user_name = user.first_name or user.username or f"Usuario {user_id}"
        mensaje_texto = event.message.text

        logger.info(f"[{nombre_sesion}] 📨 {user_name}: {mensaje_texto[:50]}...")

        # Verificar rate limit
        if not verificar_rate_limit(user_id):
            logger.warning(f"[{nombre_sesion}] ⚠️ Rate limit excedido para {user_name}")
            await event.reply("Estás enviando mensajes muy rápido. Espera un momento. ⏱️")
            return

        # Crear o actualizar usuario en BD
        db_user_id, es_nuevo = db.crear_o_actualizar_usuario(
            telegram_id=user_id,
            nombre=user_name,
            username=user.username
        )

        # Obtener usuario actual para saber su país
        usuario_bd = db.obtener_usuario(user_id)
        pais_actual = usuario_bd.get('pais') if usuario_bd else None

        # Detectar país automáticamente
        pais_detectado = detectar_pais(mensaje_texto, pais_actual)

        # Registrar detección si es nueva
        if pais_detectado != pais_actual:
            db.registrar_deteccion_pais(db_user_id, pais_detectado, 'palabra_clave', 0.8)
            logger.info(f"[{nombre_sesion}] 🌍 País: {pais_detectado}")

        # Registrar auditoría
        db.registrar_auditoria(db_user_id, "mensaje_recibido", {
            "mensaje_preview": mensaje_texto[:100],
            "pais_detectado": pais_detectado,
            "sesion": nombre_sesion
        })

        try:
            # Generar respuesta con IA
            respuesta_ia = await generar_respuesta_ia(
                mensaje_usuario=mensaje_texto,
                usuario_id=user_id,
                user_name=user_name,
                pais=pais_detectado,
                ai_client=ai_client,
                config=config,
                conversation_history=conversation_history
            )

            # Guardar conversación en BD con sesion
            db.guardar_conversacion(
                usuario_id=db_user_id,
                mensaje_usuario=mensaje_texto,
                respuesta_bot=respuesta_ia,
                pais_detectado=pais_detectado,
                cuenta_sesion=nombre_sesion
            )

            # Enviar respuesta
            await event.reply(respuesta_ia)
            logger.info(f"[{nombre_sesion}] ✅ Respuesta enviada a {user_name}")

        except Exception as e:
            logger.error(f"[{nombre_sesion}] ❌ Error en mensaje: {e}")
            await event.reply("Tuve un problema. Intenta de nuevo. 😅")

    client.add_event_handler(handle_text_message, events.NewMessage(incoming=True))
    logger.info(f"[{nombre_sesion}] ✓ Handler de texto registrado")


async def registrar_handler_media(client, db, receptor_user_id: int, nombre_sesion: str):
    """
    Registra el handler de imágenes para reenvio automático de comprobantes de pago.
    """

    async def handle_media_message(event):
        # Ignorar grupos y canales
        if event.is_group or event.is_channel:
            return

        # Verificar que sea una imagen/foto
        if not event.message.media:
            return

        es_foto = isinstance(event.message.media, MessageMediaPhoto)
        if not es_foto:
            return

        user = await event.get_sender()
        user_id = user.id
        user_name = user.first_name or user.username or f"Usuario {user_id}"

        logger.info(f"[{nombre_sesion}] 📸 Comprobante de {user_name}")

        try:
            # Reenviar la foto al receptor (operador)
            await client.forward_messages(
                entity=receptor_user_id,
                messages=event.message,
                from_peer=event.chat_id
            )

            # Agregar mensaje con info del remitente
            await client.send_message(
                receptor_user_id,
                f"💰 Comprobante de: {user_name} (ID: {user_id})\n"
                f"Sesión: {nombre_sesion}\n"
                f"Hora: {datetime.now().strftime('%H:%M:%S')}"
            )

            # Responder al cliente
            await event.reply(
                "✅ Recibimos tu comprobante, lo estamos verificando.\n"
                "En breve te confirmo el acceso a los datos.\n"
                f"Tiempo de confirmación: {obtener_tiempo_confirmacion(user.id, db)}"
            )

            logger.info(f"[{nombre_sesion}] ✅ Comprobante reenviado a receptor")

        except Exception as e:
            logger.error(f"[{nombre_sesion}] ❌ Error reenviando comprobante: {e}")
            await event.reply("Recibimos tu imagen. La revisaremos ahora mismo. ⏳")

    client.add_event_handler(handle_media_message, events.NewMessage(incoming=True))
    logger.info(f"[{nombre_sesion}] ✓ Handler de media registrado")


def detectar_pais(mensaje: str, pais_anterior: str = None) -> str:
    """Detección simple de país por palabras clave"""
    paises_keywords = {
        'Argentina': ['argentina', 'buenos aires', 'ars', 'pesos'],
        'Brasil': ['brasil', 'são paulo', 'brl', 'real'],
        'Venezuela': ['venezuela', 'caracas', 'ves'],
        'México': ['méxico', 'mexico', 'cdmx', 'mxn'],
        'Colombia': ['colombia', 'bogotá', 'cop'],
        'Perú': ['perú', 'peru', 'lima', 'pen'],
        'Chile': ['chile', 'santiago', 'clp'],
    }

    mensaje_lower = mensaje.lower()
    for pais, palabras in paises_keywords.items():
        for palabra in palabras:
            if palabra in mensaje_lower:
                return pais

    return pais_anterior if pais_anterior else 'Internacional'


async def generar_respuesta_ia(mensaje_usuario: str, usuario_id: int, user_name: str,
                              pais: str, ai_client: Anthropic, config: dict,
                              conversation_history: dict) -> str:
    """Genera respuesta usando Claude IA"""

    if usuario_id not in conversation_history:
        conversation_history[usuario_id] = []

    # Agregar mensaje del usuario
    conversation_history[usuario_id].append({
        "role": "user",
        "content": mensaje_usuario
    })

    # Limitar historial a últimos 10 mensajes
    mensajes_contexto = conversation_history[usuario_id][-10:]

    # Obtener prompt personalizado por país
    system_prompt = obtener_system_prompt(pais, config)

    try:
        response = ai_client.messages.create(
            model="claude-opus-4-7",
            max_tokens=512,
            system=system_prompt,
            messages=mensajes_contexto
        )

        respuesta = response.content[0].text

        # Guardar en historial
        conversation_history[usuario_id].append({
            "role": "assistant",
            "content": respuesta
        })

        logger.info(f"💬 {user_name} → {respuesta[:50]}...")
        return respuesta

    except Exception as e:
        logger.error(f"❌ Error IA: {e}")
        return "Disculpa, tuve un error. Intenta de nuevo. 😅"


def obtener_tiempo_confirmacion(user_id: int, db) -> str:
    """Obtiene el tiempo de confirmación según el país"""
    usuario = db.obtener_usuario(user_id)
    if not usuario:
        return "Inmediata (sin especificar país)"

    pais = usuario.get('pais', 'Internacional')
    tiempos = {
        'Argentina': 'Inmediata',
        'Brasil': 'Inmediata',
        'México': 'Inmediata',
        'Colombia': 'Inmediata',
        'Venezuela': '9 AM a 1 AM',
        'Uruguay': '9 AM a 12 AM',
        'Perú': '9 AM a 1 AM',
        'Chile': '9 AM a 12 AM'
    }
    return tiempos.get(pais, 'Inmediata')
