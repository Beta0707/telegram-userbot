"""
Handlers de mensajes para el userbot multi-cuenta.
Maneja mensajes de texto (IA) y media (reenvio de comprobantes de pago).
"""

import asyncio
import random
import logging
import os
import tempfile
import subprocess
import httpx
from datetime import datetime, timedelta
from telethon import events
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
from anthropic import Anthropic
from prompt_vendedor import obtener_system_prompt

try:
    from PIL import Image
    PYTESSERACT_AVAILABLE = True
except ImportError:
    PYTESSERACT_AVAILABLE = False

TESSERACT_PATH = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
NTFY_CANAL = "Million_Game"


async def enviar_notificacion_ntfy(user_name: str, pais: str = "Internacional"):
    """Envía notificación push a ntfy.sh con país y emojis"""
    try:
        bandera_emoji = {
            'Argentina': '🇦🇷', 'Brasil': '🇧🇷', 'Venezuela': '🇻🇪', 'Uruguay': '🇺🇾',
            'Perú': '🇵🇪', 'Costa Rica': '🇨🇷', 'Chile': '🇨🇱', 'México': '🇲🇽',
            'Internacional': '🌍'
        }.get(pais, '🌍')

        hora = datetime.now().strftime('%H:%M:%S')
        mensaje = f"{bandera_emoji} {user_name}\n{pais} | {hora}"
        titulo = "COMPROBANTE RECIBIDO"

        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(
                f"https://ntfy.sh/{NTFY_CANAL}",
                content=mensaje,
                headers={
                    "Title": titulo,
                    "Priority": "high",
                    "Tags": "money,check"
                }
            )
            logger.info(f"✅ Notificación enviada: {user_name} ({pais})")
    except Exception as e:
        logger.warning(f"⚠️ Error ntfy: {e}")


async def procesar_cola_forwards(client, receptor_user_id, db, nombre_sesion):
    """Procesa la cola de forwards secuencialmente para evitar rate limit"""
    global queue_processor_running
    queue_processor_running = True

    while True:
        try:
            tarea = await asyncio.wait_for(forward_queue.get(), timeout=1.0)
            user_id, user_name, event, pais = tarea

            try:
                await asyncio.sleep(random.uniform(3, 5))
                await client.forward_messages(
                    entity=receptor_user_id,
                    messages=event.message,
                    from_peer=event.chat_id
                )

                await asyncio.sleep(1)
                await client.send_message(
                    receptor_user_id,
                    f"Comprobante de: {user_name} (ID: {user_id}) | Sesion: {nombre_sesion} | {datetime.now().strftime('%H:%M:%S')}"
                )

                db.registrar_imagen_reenviada(user_id)
                logger.info(f"[{nombre_sesion}] Comprobante reenviado al receptor")

                await enviar_notificacion_ntfy(user_name, pais)

            except Exception as e:
                logger.error(f"[{nombre_sesion}] Error en cola: {e}")

            forward_queue.task_done()

        except asyncio.TimeoutError:
            continue
        except Exception as e:
            logger.error(f"Error en procesador de cola: {e}")
            await asyncio.sleep(1)

logger = logging.getLogger(__name__)

MAX_MESSAGES_PER_MINUTE = 5

forward_queue = asyncio.Queue()
queue_processor_running = False

# Palabras prohibidas / insultos en español
PALABRAS_PROHIBIDAS = [
    'puta', 'mierda', 'idiota', 'estupido', 'imbecil', 'hdp', 'concha',
    'pelotudo', 'boludo', 'pendejo', 'joder', 'coño', 'carajo', 'fuck',
    'shit', 'hijo de puta', 'la concha', 'gilpollas', 'gilipollas',
    'malparido', 'marica', 'maricon', 'puto', 'guevon', 'culero', 'verga',
    'chinga', 'cabron', 'bastardo', 'imbécil', 'estúpido'
]

RESPUESTA_INSULTO = "Solo vendemos grupos con contenido."
RESPUESTA_RATE_LIMIT = "Un momento por favor."

PALABRAS_CLAVE_COMPROBANTE = [
    'transferencia', 'pago', 'comprobante', 'confirmación', 'confirmacion',
    'confirmacion', 'receipt', 'invoice', 'factura', 'recibido', 'deposito',
    'cvu', 'cbu', 'pix', 'banesco', 'movil', 'usd', 'ars', 'brl', 'clp',
    'send', 'sent', 'transaction', 'transaccion', 'transacción', 'payment',
    'realizado', 'exitoso', 'exito', 'aceptado', 'completado', 'aprobado',
    'listo', 'de', 'para', 'monto', 'nombre', 'destinatario', 'entidad',
    'enviaron', 'envio', 'importe', 'transferido', 'destino', 'yapeaste',
    'cuenta', 'origen', 'operacion', 'operación', 'identificacion', 'identificación',
    'concepto', 'efectivo', 'tarjeta', 'remitente', 'carga', 'exitosa'
]


async def es_comprobante_pago(client, mensaje) -> bool:
    """Detecta si la imagen es un comprobante de pago usando OCR"""
    if not PYTESSERACT_AVAILABLE or not os.path.exists(TESSERACT_PATH):
        logger.warning("OCR no disponible, permitiendo todas las imágenes")
        return True

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            ruta_imagen = await client.download_media(mensaje.media, file=temp_dir)
            if not ruta_imagen:
                logger.warning("No se pudo descargar imagen")
                return True

            # Ejecutar tesseract directamente
            ruta_txt = os.path.join(temp_dir, "ocr_result")
            resultado = subprocess.run(
                [TESSERACT_PATH, ruta_imagen, ruta_txt, "-l", "eng+spa"],
                capture_output=True,
                timeout=10
            )

            ruta_txt_file = ruta_txt + ".txt"
            if not os.path.exists(ruta_txt_file):
                logger.warning("OCR no generó salida")
                return True

            with open(ruta_txt_file, 'r', encoding='utf-8') as f:
                texto = f.read().lower()

            detecciones = sum(1 for palabra in PALABRAS_CLAVE_COMPROBANTE if palabra in texto)
            logger.info(f"OCR: {detecciones} palabras detectadas")

            return detecciones >= 1

    except Exception as e:
        logger.error(f"Error OCR: {e}")
        logger.warning("Permitiendo imagen por error OCR")
        return True


async def registrar_handler_texto(client, ai_client: Anthropic, db, config: dict,
                                  conversation_history: dict, user_message_times: dict,
                                  nombre_sesion: str):
    """
    Registra el handler de mensajes de texto (IA).
    Responde con cooldown humano de 8-20 segundos.
    No guarda historial en BD, solo en memoria.
    """

    message_buffer = {}
    buffer_tasks = {}
    BUFFER_TIMEOUT = 3

    def verificar_rate_limit(user_id: int) -> bool:
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

    def contiene_insulto(texto: str) -> bool:
        texto_lower = texto.lower()
        return any(palabra in texto_lower for palabra in PALABRAS_PROHIBIDAS)

    async def procesar_buffer_usuario(user_id, user_name):
        try:
            await asyncio.sleep(BUFFER_TIMEOUT)
            eventos = message_buffer.get(user_id, [])

            if not eventos:
                return

            # Procesar todos los eventos del buffer
            mensajes_textos = [evt.message.text for evt in eventos]
            mensaje_combinado = "\n".join(mensajes_textos)

            logger.info(f"[{nombre_sesion}] Procesando {len(eventos)} mensaje(s) de {user_name}")

            # Rate limit check para el primer mensaje
            if not verificar_rate_limit(user_id):
                logger.warning(f"[{nombre_sesion}] Rate limit: {user_name}")
                cooldown = random.uniform(8, 20)
                await asyncio.sleep(cooldown)
                await eventos[0].reply(RESPUESTA_RATE_LIMIT)
                message_buffer[user_id] = []
                return

            # Registrar usuario
            db_user_id, es_nuevo = db.crear_o_actualizar_usuario(
                telegram_id=user_id,
                nombre=user_name,
                username=eventos[0].sender.username if hasattr(eventos[0], 'sender') else None
            )

            # Detectar insultos en cualquier mensaje
            contiene_insultos = any(contiene_insulto(texto) for texto in mensajes_textos)
            if contiene_insultos:
                logger.info(f"[{nombre_sesion}] Insulto detectado de {user_name}")
                cooldown = random.uniform(8, 20)
                await asyncio.sleep(cooldown)
                await eventos[0].reply(RESPUESTA_INSULTO)
                message_buffer[user_id] = []
                return

            # Obtener país guardado
            usuario_bd = db.obtener_usuario(user_id)
            pais_guardado = usuario_bd.get('pais') if usuario_bd else None
            pais_detectado = detectar_pais(mensaje_combinado, pais_guardado)

            if pais_detectado and pais_detectado != 'Internacional' and pais_detectado != pais_guardado:
                db.registrar_deteccion_pais(db_user_id, pais_detectado, 'palabra_clave', 0.8)
                logger.info(f"[{nombre_sesion}] País detectado: {pais_detectado}")

            # Generar respuesta
            respuesta_ia = await generar_respuesta_ia(
                mensaje_usuario=mensaje_combinado,
                usuario_id=user_id,
                user_name=user_name,
                pais=pais_detectado,
                ai_client=ai_client,
                config=config,
                conversation_history=conversation_history
            )

            # Filtro de "vendemos" - prepend si se menciona
            if any("vendemos" in texto.lower() for texto in mensajes_textos):
                respuesta_ia = "Sí, vendemos grupos con contenido. " + respuesta_ia

            # Cooldown
            cooldown = random.uniform(8, 20)
            logger.info(f"[{nombre_sesion}] Cooldown {cooldown:.1f}s para {user_name}...")
            await asyncio.sleep(cooldown)

            # Responder
            await eventos[0].reply(respuesta_ia)
            logger.info(f"[{nombre_sesion}] Respuesta enviada a {user_name}")

        except Exception as e:
            logger.error(f"[{nombre_sesion}] Error procesando buffer: {e}")
        finally:
            message_buffer[user_id] = []
            if user_id in buffer_tasks:
                del buffer_tasks[user_id]

    async def handle_text_message(event):
        # FILTRO 1: Ignorar grupos y canales
        if event.is_group or event.is_channel:
            return

        # FILTRO 2: Ignorar si no tiene texto
        if not event.message.text:
            return

        # FILTRO 3: Ignorar si es media
        if event.message.media:
            return

        user = await event.get_sender()

        # FILTRO 4: NUNCA responder a bots
        if user.bot:
            logger.info(f"[{nombre_sesion}] Ignorado mensaje de bot: {user.first_name}")
            return

        # FILTRO 5: NUNCA responder a mensajes largos (>300 chars = gasto innecesario)
        MAX_CHARS = 300
        if len(event.message.text) > MAX_CHARS:
            logger.info(f"[{nombre_sesion}] ⏭️ Mensaje ignorado (demasiado largo)")
            return

        user_id = user.id
        user_name = user.first_name or user.username or f"Usuario {user_id}"

        logger.info(f"[{nombre_sesion}] 📨 Mensaje recibido de {user_name}")

        # Agregar al buffer
        if user_id not in message_buffer:
            message_buffer[user_id] = []
        message_buffer[user_id].append(event)

        # Si ya hay un timer activo, solo agregar al buffer
        if user_id in buffer_tasks:
            logger.info(f"[{nombre_sesion}] Mensaje agregado al buffer de {user_name}")
            return

        # Crear timer para procesar el buffer
        task = asyncio.create_task(procesar_buffer_usuario(user_id, user_name))
        buffer_tasks[user_id] = task

    client.add_event_handler(handle_text_message, events.NewMessage(incoming=True))
    logger.info(f"[{nombre_sesion}] Handler de texto registrado")


async def registrar_handler_media(client, db, receptor_user_id: int, nombre_sesion: str,
                                  ai_client: Anthropic = None, config: dict = None,
                                  conversation_history: dict = None, user_message_times: dict = None):
    """
    Registra el handler de imágenes.
    Si hay texto + imagen → responde el texto.
    Si solo imagen → verifica si es comprobante y reenvía (via cola).
    """
    global queue_processor_running

    # Iniciar procesador de cola una sola vez
    if not queue_processor_running:
        asyncio.create_task(procesar_cola_forwards(client, receptor_user_id, db, nombre_sesion))

    async def handle_media_message(event):
        # Ignorar grupos y canales
        if event.is_group or event.is_channel:
            return

        # Verificar que tenga media
        if not event.message.media:
            return

        # Aceptar fotos y documentos
        es_foto = isinstance(event.message.media, MessageMediaPhoto)
        es_documento = isinstance(event.message.media, MessageMediaDocument)

        if not es_foto and not es_documento:
            return

        user = await event.get_sender()
        user_id = user.id
        user_name = user.first_name or user.username or f"Usuario {user_id}"
        mensaje_texto = event.message.text or ""

        logger.info(f"[{nombre_sesion}] Imagen recibida de {user_name}")

        # CASO 1: Si hay texto + imagen, responder el texto SIEMPRE
        if mensaje_texto and ai_client and config and conversation_history:
            logger.info(f"[{nombre_sesion}] Imagen con texto, respondiendo mensaje")

            usuario_bd = db.obtener_usuario(user_id)
            pais_guardado = usuario_bd.get('pais') if usuario_bd else None
            pais_detectado = detectar_pais(mensaje_texto, pais_guardado)

            try:
                respuesta_ia = await generar_respuesta_ia(
                    mensaje_usuario=mensaje_texto,
                    usuario_id=user_id,
                    user_name=user_name,
                    pais=pais_detectado,
                    ai_client=ai_client,
                    config=config,
                    conversation_history=conversation_history
                )

                cooldown = random.uniform(8, 20)
                await asyncio.sleep(cooldown)
                await event.reply(respuesta_ia)
                logger.info(f"[{nombre_sesion}] Respuesta enviada")
            except Exception as e:
                logger.error(f"[{nombre_sesion}] Error respondiendo: {e}")

            # Siempre intentar reenviar si es comprobante (incluso con texto)
            if await es_comprobante_pago(client, event.message):
                try:
                    await asyncio.sleep(random.uniform(3, 5))
                    await client.forward_messages(
                        entity=receptor_user_id,
                        messages=event.message,
                        from_peer=event.chat_id
                    )
                    await asyncio.sleep(1)
                    await client.send_message(
                        receptor_user_id,
                        f"Comprobante de: {user_name} (ID: {user_id}) | Sesion: {nombre_sesion} | {datetime.now().strftime('%H:%M:%S')}"
                    )
                    db.registrar_imagen_reenviada(user_id)
                    logger.info(f"[{nombre_sesion}] Comprobante reenviado al receptor")
                except Exception as e:
                    logger.error(f"[{nombre_sesion}] Error reenviando: {e}")
            return

        # CASO 2: Solo imagen, sin texto - filtrar por comprobante
        if not await es_comprobante_pago(client, event.message):
            logger.info(f"[{nombre_sesion}] Imagen ignorada (no es comprobante)")
            return

        # Detectar país para la notificación
        usuario_bd = db.obtener_usuario(user_id)
        pais_guardado = usuario_bd.get('pais') if usuario_bd else None

        # Agregar a cola de forwards (procesa secuencialmente)
        await forward_queue.put((user_id, user_name, event, pais_guardado or 'Internacional'))
        logger.info(f"[{nombre_sesion}] Comprobante agregado a cola")

    client.add_event_handler(handle_media_message, events.NewMessage(incoming=True))
    logger.info(f"[{nombre_sesion}] Handler de media registrado")


def detectar_pais(mensaje: str, pais_anterior: str = None) -> str:
    """Detecta el país del usuario por palabras clave en el mensaje"""
    paises_keywords = {
        'Argentina': ['argentina', 'arg', 'buenos aires', 'rosario', 'córdoba', 'cordoba',
                      'mendoza', 'ars', 'peso argentino', 'mercadopago', 'mercado pago',
                      'alias', 'cbu', 'cvu', 'vos', 'che'],
        'Brasil': ['brasil', 'brazil', 'são paulo', 'sao paulo', 'rio de janeiro',
                   'brasilia', 'brl', 'real', 'reais', 'pix'],
        'Venezuela': ['venezuela', 'caracas', 'maracaibo', 'valencia', 'ves',
                      'bolivares', 'pago movil', 'banesco', 'zelle'],
        'México': ['méxico', 'mexico', 'cdmx', 'guadalajara', 'monterrey', 'mxn',
                   'peso mexicano', 'oxxo', 'spei', 'banamex', 'bbva mexico'],
        'Colombia': ['colombia', 'bogotá', 'bogota', 'medellin', 'cali', 'cop',
                     'peso colombiano', 'nequi', 'bancolombia', 'daviplata'],
        'Perú': ['perú', 'peru', 'lima', 'arequipa', 'cusco', 'pen',
                 'soles', 'yape', 'plin', 'bcp'],
        'Chile': ['chile', 'santiago', 'valparaiso', 'clp', 'pesos chilenos', 'bci', 'scotiabank chile'],
        'Uruguay': ['uruguay', 'montevideo', 'uyu', 'pesos uruguayos', 'brou', 'prex'],
        'Ecuador': ['ecuador', 'quito', 'guayaquil', 'pichincha'],
        'Costa Rica': ['costa rica', 'san jose', 'crc', 'colones', 'sinpe'],
        'Honduras': ['honduras', 'tegucigalpa', 'lempiras', 'lps'],
        'Paraguay': ['paraguay', 'asuncion', 'guaranies', 'pyg'],
        'Internacional': ['usa', 'eeuu', 'estados unidos', 'usd', 'dolar', 'dollar',
                          'españa', 'españa', 'europa', 'venmo', 'paypal', 'western union'],
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
    """
    Genera respuesta usando Claude IA.
    Mantiene historial en memoria (no en BD).
    """

    if usuario_id not in conversation_history:
        conversation_history[usuario_id] = []

    # Agregar mensaje del usuario al historial en memoria
    conversation_history[usuario_id].append({
        "role": "user",
        "content": mensaje_usuario
    })

    # Limitar historial a últimos 20 mensajes para mayor contexto
    mensajes_contexto = conversation_history[usuario_id][-20:]

    # Obtener prompt con precios del país
    system_prompt = obtener_system_prompt(pais, config)

    try:
        response = ai_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            system=system_prompt,
            messages=mensajes_contexto
        )

        respuesta = response.content[0].text

        # Guardar respuesta en historial en memoria
        conversation_history[usuario_id].append({
            "role": "assistant",
            "content": respuesta
        })

        logger.info(f"IA para {user_name}: {respuesta[:60]}...")
        return respuesta

    except Exception as e:
        logger.error(f"Error IA: {e}")
        return "Solo vendemos grupos con contenido."
