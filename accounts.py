"""
Gestor de cuentas multi-Telegram para el userbot.
Carga, conecta y desconecta múltiples cuentas desde .env
"""

import os
import logging
from telethon import TelegramClient

logger = logging.getLogger(__name__)


def cargar_cuentas(api_id: int, api_hash: str) -> list:
    """
    Carga la configuración de todas las cuentas desde variables de entorno.
    Retorna lista de dicts con {client, phone, session_name, numero, tiene_sesion}
    """
    cuentas = []

    for i in range(1, 4):  # Cuentas 1, 2, 3
        phone = os.getenv(f'TELEGRAM_PHONE_{i}', '').strip()
        session = os.getenv(f'TELEGRAM_SESSION_{i}', f'session_cuenta{i}')

        # Verificar si la sesión ya existe (archivo .session)
        session_file = f"{session}.session"
        sesion_existe = os.path.isfile(session_file)

        # Lógica de decisión
        if not phone and not sesion_existe:
            # Sin número Y sin sesión → Saltarla
            logger.info(f"Cuenta {i}: No configurada (sin teléfono y sin sesión), saltando")
            continue
        elif not phone and sesion_existe:
            # Sin número PERO con sesión → Usarla
            logger.info(f"Cuenta {i}: Sesión existente encontrada ({session})")
            phone = None
        elif phone and not sesion_existe:
            # Con número PERO sin sesión → Crear nueva
            logger.info(f"Cuenta {i}: Se creará nueva sesión con {phone}")
        elif phone and sesion_existe:
            # Con número Y con sesión → Usar sesión existente (ignorar número)
            logger.info(f"Cuenta {i}: Usando sesión existente {session} (ignorando número)")
            phone = None

        client = TelegramClient(session, api_id, api_hash)
        cuentas.append({
            'client': client,
            'phone': phone,
            'session_name': session,
            'numero': i,
            'tiene_sesion': sesion_existe
        })
        estado = f"({phone})" if phone else "(sesión existente)"
        logger.info(f"✓ Cuenta {i} configurada: {session} {estado}")

    return cuentas


async def conectar_cuenta(cuenta: dict) -> bool:
    """
    Conecta y autentica una cuenta.
    Si la sesión existe, reconecta automáticamente.
    Si no existe y no hay número, la saltea (no pide código).
    Retorna True si se conectó exitosamente.
    """
    client = cuenta['client']
    phone = cuenta['phone']
    session_name = cuenta['session_name']
    numero = cuenta['numero']
    tiene_sesion = cuenta.get('tiene_sesion', False)

    # Si no hay teléfono Y no tiene sesión → Saltarla sin intentar
    if not phone and not tiene_sesion:
        logger.warning(f"⚠️ [{session_name}] No hay sesión ni teléfono configurado, saltando")
        return False

    # Si no hay teléfono pero SÍ tiene sesión → Reconectar
    if not phone and tiene_sesion:
        try:
            logger.info(f"[{session_name}] Reconectando con sesión existente...")
            await client.start()
            me = await client.get_me()
            logger.info(f"✅ [{session_name}] Conectado como: {me.first_name} (@{me.username})")
            return True
        except Exception as e:
            logger.error(f"❌ [{session_name}] Error en sesión existente: {e}")
            return False

    # Si hay teléfono → Conectar con él
    try:
        logger.info(f"[{session_name}] Conectando con número: {phone}")
        await client.start(phone=phone)
        me = await client.get_me()
        logger.info(f"✅ [{session_name}] Conectado como: {me.first_name} (@{me.username})")
        return True
    except Exception as e:
        logger.error(f"❌ [{session_name}] Error conectando: {e}")
        return False


async def desconectar_todas(cuentas: list):
    """Desconecta todas las cuentas"""
    for cuenta in cuentas:
        try:
            await cuenta['client'].disconnect()
            logger.info(f"[{cuenta['session_name']}] Desconectado")
        except Exception as e:
            logger.warning(f"Error desconectando {cuenta['session_name']}: {e}")
