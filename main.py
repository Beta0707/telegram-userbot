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
from anthropic import Anthropic

from accounts import cargar_cuentas, conectar_cuenta, desconectar_todas
from handlers import registrar_handler_texto, registrar_handler_media
from database_completa import inicializar_bd

load_dotenv()

# ============= CONFIGURACIÓN DE LOGGING =============

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/userbot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============= CREDENCIALES =============

API_ID = int(os.getenv('TELEGRAM_API_ID', '0'))
API_HASH = os.getenv('TELEGRAM_API_HASH', '')
ANTHROPIC_KEY = os.getenv('ANTHROPIC_API_KEY', '')
RECEPTOR_USER_ID = int(os.getenv('RECEPTOR_USER_ID', '0'))
DB_PATH = os.getenv('DB_PATH', 'userbot_completo.db')

# ============= CLIENTES Y SERVICIOS =============

ai_client = Anthropic(api_key=ANTHROPIC_KEY)
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
            stats = db.obtener_estadisticas()
            logger.info(f"""
╔═══════════════════════════════════════════╗
║         📊 ESTADÍSTICAS DEL BOT            ║
╠═══════════════════════════════════════════╣
║  👥 Total usuarios: {stats['total_usuarios']:>20} ║
║  🌍 Países activos: {stats['paises_activos']:>21} ║
║  📦 Órdenes totales: {stats['total_ordenes']:>19} ║
║  ✅ Órdenes pagadas: {stats['ordenes_pagadas']:>19} ║
║  ⏳ Órdenes pendientes: {stats['ordenes_pendientes']:>16} ║
║  💰 Ventas USD: ${stats['ventas_total_usd']:>20.2f} ║
║  💬 Conversaciones: {stats['total_conversaciones']:>19} ║
╚═══════════════════════════════════════════╝
""")
        except Exception as e:
            logger.error(f"Error obteniendo estadísticas: {e}")


# ============= MENÚ INTERACTIVO =============

def mostrar_menu():
    """Muestra un menú al iniciar el bot"""
    print("\n" + "=" * 60)
    print("🤖 USERBOT MULTI-CUENTA CON IA ANTHROPIC")
    print("=" * 60)
    print("\n¿Qué deseas hacer?\n")
    print("  1) Usar sesiones EXISTENTES (sin pedir códigos)")
    print("  2) Agregar NUEVA CUENTA (pedir teléfono)")
    print("  3) Salir\n")

    while True:
        opcion = input("Selecciona una opción (1, 2 o 3): ").strip()
        if opcion in ['1', '2', '3']:
            return opcion
        print("❌ Opción inválida, intenta de nuevo\n")


# ============= PUNTO DE ENTRADA =============


async def main():
    """Inicia el userbot multi-cuenta"""

    # Verificar credenciales críticas
    if not API_ID or not API_HASH or not ANTHROPIC_KEY:
        logger.error("❌ Faltan credenciales en .env:")
        logger.error(f"   TELEGRAM_API_ID: {'✅' if API_ID else '❌'}")
        logger.error(f"   TELEGRAM_API_HASH: {'✅' if API_HASH else '❌'}")
        logger.error(f"   ANTHROPIC_API_KEY: {'✅' if ANTHROPIC_KEY else '❌'}")
        return

    if not RECEPTOR_USER_ID:
        logger.error("❌ RECEPTOR_USER_ID no configurado en .env")
        return

    # Crear carpeta de logs si no existe
    os.makedirs('logs', exist_ok=True)

    # Mostrar menú
    opcion = mostrar_menu()

    if opcion == '3':
        print("❌ Saliendo...")
        return

    logger.info("=" * 60)
    logger.info("🤖 USERBOT MULTI-CUENTA CON IA ANTHROPIC")
    logger.info("=" * 60)

    # Cargar cuentas desde .env
    cuentas = cargar_cuentas(API_ID, API_HASH)

    # Si el usuario eligió opción 2 (agregar nueva cuenta), pedir teléfono
    if opcion == '2' and cuentas:
        print("\n📱 AGREGAR NUEVA CUENTA")
        print("Cuál cuenta deseas agregar?")
        for cuenta in cuentas:
            print(f"  - Cuenta {cuenta['numero']} ({cuenta['session_name']})")
        numero_str = input("\nIngresa el número (1, 2 o 3): ").strip()
        if numero_str in ['1', '2', '3']:
            numero_idx = int(numero_str) - 1
            if numero_idx < len(cuentas):
                numero_telefono = input("Ingresa tu teléfono (+5491123456789): ").strip()
                if numero_telefono.startswith('+'):
                    cuentas[numero_idx]['phone'] = numero_telefono
                    print(f"✅ Teléfono agregado: {numero_telefono}")
                else:
                    print("❌ Formato inválido, debe empezar con +")
                    return

    if not cuentas:
        logger.error("❌ No hay cuentas configuradas")
        logger.error("   Configura TELEGRAM_PHONE_1, TELEGRAM_PHONE_2, TELEGRAM_PHONE_3 en .env")
        return

    logger.info(f"📱 Cuentas a conectar: {len(cuentas)}")

    # Conectar todas las cuentas
    cuentas_activas = []
    for cuenta in cuentas:
        ok = await conectar_cuenta(cuenta)
        if ok:
            cuentas_activas.append(cuenta)
        else:
            logger.warning(f"⚠️ Saltando cuenta {cuenta['numero']}")

    if not cuentas_activas:
        logger.error("❌ No se pudo conectar a ninguna cuenta")
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
            nombre_sesion=session_name
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
