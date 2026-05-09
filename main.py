#!/usr/bin/env python3
"""
Telegram Userbot Multi-Cuenta con IA Anthropic
Responde desde 3 cuentas de forma inteligente, reenvía comprobantes a operador.
"""

import asyncio
import logging
import os
import json
from dotenv import load_dotenv

from accounts import cargar_cuentas, conectar_cuenta, desconectar_todas
from handlers import registrar_handler_texto, registrar_handler_media
from database_completa import inicializar_bd
from broadcast import worker_broadcast

# Lazy import para Anthropic (evita problemas de httpcore)
def get_ai_client(api_key):
    from anthropic import Anthropic
    return Anthropic(api_key=api_key)

load_dotenv()

# Crear carpeta de logs primero
os.makedirs('logs', exist_ok=True)

# ============= CONFIGURACIÓN DE LOGGING =============

handlers = [logging.StreamHandler()]
try:
    handlers.append(logging.FileHandler('logs/userbot.log', encoding='utf-8'))
except Exception:
    pass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=handlers
)
logger = logging.getLogger(__name__)

# ============= CREDENCIALES =============

API_ID = int(os.getenv('TELEGRAM_API_ID', '0'))
API_HASH = os.getenv('TELEGRAM_API_HASH', '')
ANTHROPIC_KEY = os.getenv('ANTHROPIC_API_KEY', '')
RECEPTOR_USER_ID = int(os.getenv('RECEPTOR_USER_ID', '0'))
DB_PATH = os.getenv('DB_PATH', 'userbot_completo.db')

# ============= BROADCAST (REENVÍO A GRUPOS) =============
GROUP_MEDIA_ID = int(os.getenv('GROUP_MEDIA_ID', '-5006003164'))
GROUP_LINK = os.getenv('GROUP_LINK', 'https://t.me/+lIHv-XxJiZ8xM2Ex')
BROADCAST_COOLDOWN = int(os.getenv('BROADCAST_COOLDOWN_MINUTES', '5'))
BROADCAST_WAIT = int(os.getenv('BROADCAST_WAIT_HOURS', '4'))
ACCOUNT_OFFSETS = {
    1: int(os.getenv('ACCOUNT_OFFSET_MINUTES_1', '0')),
    2: int(os.getenv('ACCOUNT_OFFSET_MINUTES_2', '90')),
    3: int(os.getenv('ACCOUNT_OFFSET_MINUTES_3', '180'))
}

# ============= CLIENTES Y SERVICIOS =============

ai_client = None
db = inicializar_bd(DB_PATH)

# Estado compartido entre las 3 cuentas
conversation_history = {}  # {user_id: [mensajes]}
user_message_times = {}    # {user_id: [timestamps]}

# Cargar configuración
CONFIG_FILE = 'config_precios_completo.json' if os.path.exists('config_precios_completo.json') else 'config.json'
try:
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        CONFIG = json.load(f)
    logger.info(f"✅ Configuración cargada: {CONFIG_FILE}")
except Exception as e:
    logger.error(f"❌ Error cargando config: {e}")
    CONFIG = {}

# ============= FUNCIONES DE UTILIDAD =============


async def mostrar_estadisticas(db):
    """Muestra estadísticas cada 10 minutos"""
    while True:
        await asyncio.sleep(600)

        try:
            stats = db.obtener_estadisticas_simples()
            logger.info(
                f"STATS | Usuarios: {stats['total_usuarios']} | "
                f"Imagenes reenviadas: {stats['total_imagenes_reenviadas']}"
            )
        except Exception as e:
            logger.error(f"Error obteniendo estadísticas: {e}")




# ============= PUNTO DE ENTRADA =============


async def main():
    """Inicia el userbot multi-cuenta (auto-run, sin menú interactivo)"""

    global ai_client

    logger.info("=" * 60)
    logger.info("🤖 USERBOT MULTI-CUENTA CON IA ANTHROPIC")
    logger.info("=" * 60)

    # Verificar credenciales críticas
    if not API_ID or not API_HASH or not ANTHROPIC_KEY:
        logger.error("❌ Faltan credenciales en .env:")
        logger.error(f"   TELEGRAM_API_ID: {'✅' if API_ID else '❌'}")
        logger.error(f"   TELEGRAM_API_HASH: {'✅' if API_HASH else '❌'}")
        logger.error(f"   ANTHROPIC_API_KEY: {'✅' if ANTHROPIC_KEY else '❌'}")
        logger.info("⏳ Esperando a que se configuren las credenciales...")
        await asyncio.sleep(60)
        return

    if not RECEPTOR_USER_ID:
        logger.warning("⚠️ RECEPTOR_USER_ID no configurado - reenvío de comprobantes deshabilitado")

    # Crear carpeta de logs si no existe
    os.makedirs('logs', exist_ok=True)

    # Inicializar cliente de Anthropic (lazy import)
    try:
        ai_client = get_ai_client(ANTHROPIC_KEY)
        logger.info("✅ Cliente Anthropic inicializado")
    except Exception as e:
        logger.error(f"❌ Error inicializando Anthropic: {e}")
        logger.info("⏳ Esperando que se resuelva el problema...")
        await asyncio.sleep(60)
        return

    # Cargar cuentas desde .env (usa sesiones existentes automáticamente)
    cuentas = cargar_cuentas(API_ID, API_HASH)

    if not cuentas:
        logger.warning("⚠️ No hay cuentas configuradas en .env")
        logger.info("   Configura TELEGRAM_PHONE_1, TELEGRAM_PHONE_2, TELEGRAM_PHONE_3 en .env")
        logger.info("⏳ Esperando configuración...")
        await asyncio.sleep(60)
        return

    logger.info(f"📱 Intentando conectar {len(cuentas)} cuenta(s)...")

    # Conectar todas las cuentas
    cuentas_activas = []
    for cuenta in cuentas:
        ok = await conectar_cuenta(cuenta)
        if ok:
            cuentas_activas.append(cuenta)
        else:
            logger.warning(f"⚠️ Saltando cuenta {cuenta['numero']} (sesión no disponible)")

    if not cuentas_activas:
        logger.warning("⚠️ No se pudo conectar a ninguna cuenta")
        logger.info("   Asegúrate de que los archivos .session existan y sean válidos")
        logger.info("⏳ Esperando conexión...")
        await asyncio.sleep(60)
        return

    logger.info(f"✅ Conectado a {len(cuentas_activas)} cuenta(s)")

    # Registrar handlers en cada cuenta activa
    logger.info("👂 Registrando handlers de mensajes...")
    for cuenta in cuentas_activas:
        client = cuenta['client']
        session_name = cuenta['session_name']

        # Handler de texto (IA)
        await registrar_handler_texto(
            client=client,
            ai_client=ai_client,
            db=db,
            config=CONFIG,
            conversation_history=conversation_history,
            user_message_times=user_message_times,
            nombre_sesion=session_name
        )

        # Handler de media (reenvio de comprobantes)
        await registrar_handler_media(
            client=client,
            db=db,
            receptor_user_id=RECEPTOR_USER_ID,
            nombre_sesion=session_name,
            ai_client=ai_client,
            config=CONFIG,
            conversation_history=conversation_history,
            user_message_times=user_message_times
        )

    # Cargar precios en BD si están en config
    if 'plantilla_precios' in CONFIG:
        logger.info("📊 Cargando precios en BD...")
        db.cargar_precios_desde_config(CONFIG)

    # Mostrar estadísticas iniciales
    stats = db.obtener_estadisticas()
    logger.info(f"📈 Estado inicial: {stats['total_usuarios']} usuarios, {stats['total_ordenes']} órdenes")

    logger.info("=" * 60)
    logger.info("✅ SISTEMAS LISTOS - Escuchando mensajes privados...")
    logger.info("=" * 60)

    try:
        # Crear tareas concurrentes
        tasks = [
            # Ejecutar los clientes
            *[cliente['client'].run_until_disconnected() for cliente in cuentas_activas],
            # Mostrar estadísticas cada 10 minutos
            mostrar_estadisticas(db)
        ]

        # Agregar workers de broadcast para cada cuenta activa
        for cuenta in cuentas_activas:
            numero_cuenta = int(cuenta['numero'])
            offset = ACCOUNT_OFFSETS.get(numero_cuenta, 0)
            tasks.append(
                worker_broadcast(
                    client=cuenta['client'],
                    account_number=numero_cuenta,
                    initial_delay_minutes=offset,
                    group_media_id=GROUP_MEDIA_ID,
                    cooldown_minutes=BROADCAST_COOLDOWN,
                    wait_hours=BROADCAST_WAIT,
                    nombre_sesion=cuenta['session_name'],
                    link_grupo=GROUP_LINK
                )
            )
            logger.info(f"📤 Worker broadcast configurado para cuenta {numero_cuenta} (offset: {offset}min)")

        # Ejecutar todas las tareas en paralelo
        await asyncio.gather(*tasks)

    except KeyboardInterrupt:
        logger.info("\n⚠️ Interrumpido por usuario")
    except Exception as e:
        logger.error(f"❌ Error fatal: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        logger.info("🛑 Desconectando...")
        await desconectar_todas(cuentas_activas)
        logger.info("✅ Desconexión completada")


# ============= PUNTO DE ENTRADA PRINCIPAL =============

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️ Interrumpido")
    except Exception as e:
        logger.error(f"❌ Error no manejado: {e}")
