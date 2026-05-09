"""
Sistema de reenvío automático de imágenes a grupos.
Cada cuenta reenvía una imagen a todos sus grupos con cooldown entre cada uno.
"""

import asyncio
import logging
from datetime import datetime
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
from telethon.tl.functions.messages import ImportChatInviteRequest

logger = logging.getLogger(__name__)


async def obtener_imagen_referencia(client, group_id: int):
    """
    Obtiene la última imagen del grupo de referencia.
    Retorna (mensaje_id, media_type) o (None, None) si no hay imagen.
    """
    try:
        async for mensaje in client.iter_messages(group_id, limit=50):
            if mensaje.media and (isinstance(mensaje.media, MessageMediaPhoto) or isinstance(mensaje.media, MessageMediaDocument)):
                logger.info(f"✅ Imagen encontrada en grupo de referencia: ID {mensaje.id}")
                return mensaje
        logger.warning(f"⚠️ No se encontraron imágenes en grupo {group_id}")
        return None
    except Exception as e:
        logger.error(f"Error obteniendo imagen: {e}")
        return None


async def obtener_grupos_usuario(client):
    """
    Obtiene lista de todos los grupos donde está la cuenta.
    Retorna lista de (chat_id, título).
    """
    grupos = []
    try:
        async for dialogo in client.iter_dialogs():
            # Solo grupos, no canales privados ni chats personales
            if dialogo.is_group:
                grupos.append((dialogo.id, dialogo.title or "Sin título"))
        logger.info(f"✅ Encontrados {len(grupos)} grupos")
        return grupos
    except Exception as e:
        logger.error(f"Error obteniendo grupos: {e}")
        return []


async def verificar_y_unirse_grupo(client, group_id: int, link_invitacion: str, nombre_sesion: str):
    """
    Verifica si estamos en el grupo. Si no, intenta unirse con el link.
    Retorna True si estamos (o nos unimos), False si hay error.
    """
    try:
        # Intentar acceder al grupo
        grupo = await client.get_entity(group_id)
        logger.info(f"[{nombre_sesion}] ✅ Ya estoy en grupo {group_id}")
        return True
    except Exception as e:
        logger.warning(f"[{nombre_sesion}] No estoy en grupo {group_id}. Intentando unirme con link...")
        try:
            # Extraer hash del link: https://t.me/+HASH
            hash_grupo = link_invitacion.split('+')[-1]
            await client(ImportChatInviteRequest(hash=hash_grupo))
            logger.info(f"[{nombre_sesion}] ✅ Me uní al grupo con éxito")
            return True
        except Exception as join_error:
            logger.error(f"[{nombre_sesion}] ❌ Error uniéndome al grupo: {join_error}")
            return False


async def worker_broadcast(client, account_number: int, initial_delay_minutes: int,
                          group_media_id: int, cooldown_minutes: int, wait_hours: int,
                          nombre_sesion: str, link_grupo: str = None):
    """
    Worker que reenvía imagen a todos los grupos de forma periódica.

    Args:
        client: Cliente de Telethon
        account_number: Número de cuenta (1, 2, 3)
        initial_delay_minutes: Minutos a esperar antes de comenzar
        group_media_id: ID del grupo donde obtener la imagen
        cooldown_minutes: Minutos entre cada reenvío
        wait_hours: Horas a esperar entre rondas
        nombre_sesion: Nombre de la sesión
        link_grupo: Link de invitación del grupo (para unirse si no está)
    """

    logger.info(f"[{nombre_sesion}] 🚀 Broadcast worker iniciado. Delay inicial: {initial_delay_minutes}min")

    # Esperar el delay inicial
    if initial_delay_minutes > 0:
        logger.info(f"[{nombre_sesion}] ⏳ Esperando {initial_delay_minutes} minutos...")
        await asyncio.sleep(initial_delay_minutes * 60)

    # Loop infinito
    while True:
        try:
            logger.info(f"[{nombre_sesion}] 📤 Iniciando ronda de reenvío")

            # Verificar si estamos en el grupo de referencia (unirse si no estamos)
            if not await verificar_y_unirse_grupo(client, group_media_id, link_grupo, nombre_sesion):
                logger.error(f"[{nombre_sesion}] Saltando ronda: no se pudo acceder al grupo de referencia")
                await asyncio.sleep(600)  # Reintentar en 10min
                continue

            # Obtener imagen
            mensaje_imagen = await obtener_imagen_referencia(client, group_media_id)
            if not mensaje_imagen:
                logger.warning(f"[{nombre_sesion}] No hay imagen para reenviar")
                await asyncio.sleep(wait_hours * 3600)
                continue

            # Obtener grupos
            grupos = await obtener_grupos_usuario(client)
            if not grupos:
                logger.warning(f"[{nombre_sesion}] No hay grupos para reenviar")
                await asyncio.sleep(wait_hours * 3600)
                continue

            # Reenviar a cada grupo con skip inteligente
            exitosos = 0
            fallos_consecutivos = 0
            for group_id, group_name in grupos:
                try:
                    # No reenviar al grupo de referencia
                    if group_id == group_media_id:
                        logger.info(f"[{nombre_sesion}] ⏭️ Saltando grupo de referencia")
                        continue

                    await client.forward_messages(
                        entity=group_id,
                        messages=mensaje_imagen,
                        from_peer=group_media_id
                    )
                    exitosos += 1
                    fallos_consecutivos = 0
                    logger.info(f"[{nombre_sesion}] ✅ Reenviado a: {group_name}")
                    await asyncio.sleep(cooldown_minutes * 60)

                except Exception as e:
                    fallos_consecutivos += 1
                    logger.warning(f"[{nombre_sesion}] ⚠️ Fallo en {group_name} ({fallos_consecutivos}/3): {e}")

                    # Reintentar una vez después de 5 segundos
                    logger.info(f"[{nombre_sesion}] 🔄 Reintentando en 5 segundos...")
                    await asyncio.sleep(5)

                    try:
                        await client.forward_messages(
                            entity=group_id,
                            messages=mensaje_imagen,
                            from_peer=group_media_id
                        )
                        exitosos += 1
                        fallos_consecutivos = 0
                        logger.info(f"[{nombre_sesion}] ✅ Reenviado (reintento) a: {group_name}")
                        await asyncio.sleep(cooldown_minutes * 60)

                    except Exception as retry_e:
                        logger.warning(f"[{nombre_sesion}] ⚠️ Reintento falló en {group_name}: {retry_e}")

                        if fallos_consecutivos >= 3:
                            logger.info(f"[{nombre_sesion}] ⏰ 3 fallos consecutivos. Esperando {cooldown_minutes}min...")
                            await asyncio.sleep(cooldown_minutes * 60)
                            fallos_consecutivos = 0

            logger.info(f"[{nombre_sesion}] ✅ Ronda completa: {exitosos}/{len(grupos)} grupos")

            # Esperar antes de siguiente ronda
            logger.info(f"[{nombre_sesion}] ⏰ Esperando {wait_hours} horas para siguiente ronda...")
            await asyncio.sleep(wait_hours * 3600)

        except Exception as e:
            logger.error(f"[{nombre_sesion}] Error en broadcast: {e}")
            await asyncio.sleep(600)  # Reintentar en 10min
