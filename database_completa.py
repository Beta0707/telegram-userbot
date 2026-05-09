import sqlite3
import json
from datetime import datetime
from typing import Optional, Dict, List, Tuple
import logging

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Gestor completo de base de datos para Telegram Userbot con IA.
    Maneja usuarios, conversaciones, órdenes, precios, métodos de pago y auditoría.
    """

    def __init__(self, db_path: str = 'userbot_completo.db'):
        self.db_path = db_path
        self.init_database()
        logger.info(f"✅ DatabaseManager inicializado: {db_path}")

    def init_database(self):
        """Crea todas las tablas necesarias si no existen"""
        conn = sqlite3.connect(self.db_path, timeout=30)
        c = conn.cursor()

        # Activar WAL mode para soportar multiples escritores concurrentes
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")

        # Tabla de usuarios
        c.execute('''CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE NOT NULL,
            nombre TEXT,
            username TEXT,
            pais TEXT,
            moneda TEXT,
            creado TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ultimo_mensaje TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        # Tabla de detección de país
        c.execute('''CREATE TABLE IF NOT EXISTS deteccion_pais (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            pais_detectado TEXT,
            metodo TEXT,
            confianza REAL DEFAULT 0.5,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
        )''')

        # Tabla de precios por país
        c.execute('''CREATE TABLE IF NOT EXISTS precios_pais (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pais TEXT NOT NULL,
            moneda TEXT,
            producto_id TEXT,
            precio_regular REAL,
            precio_descuento REAL,
            tasa_cambio REAL,
            minimo_transferencia REAL,
            confirmacion TEXT,
            UNIQUE(pais, producto_id)
        )''')

        # Tabla de métodos de pago
        c.execute('''CREATE TABLE IF NOT EXISTS metodos_pago (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pais TEXT UNIQUE NOT NULL,
            metodos TEXT,  -- JSON array
            datos_pago TEXT,  -- JSON object
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        # Tabla de órdenes
        c.execute('''CREATE TABLE IF NOT EXISTS ordenes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            producto_id TEXT,
            pais TEXT,
            moneda TEXT,
            precio_mostrado REAL,
            precio_usd REAL,
            metodo_pago TEXT,
            estado TEXT DEFAULT 'pendiente',
            referencia TEXT,
            creado TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            actualizado TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
        )''')

        # Tabla de conversaciones
        c.execute('''CREATE TABLE IF NOT EXISTS conversaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            mensaje_usuario TEXT,
            respuesta_bot TEXT,
            pais_detectado TEXT,
            cuenta_sesion TEXT,
            tokens_usados INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
        )''')

        # Tabla de plantillas enviadas
        c.execute('''CREATE TABLE IF NOT EXISTS plantillas_enviadas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            plantilla_tipo TEXT,  -- "precios", "metodos_pago", "general"
            pais TEXT,
            contenido TEXT,  -- JSON
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
        )''')

        # Tabla de auditoría
        c.execute('''CREATE TABLE IF NOT EXISTS auditoria (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER,
            accion TEXT NOT NULL,  -- "login", "pedido", "pago", "error"
            detalles TEXT,  -- JSON
            ip TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL
        )''')

        # Crear índices para mejor rendimiento
        c.execute('''CREATE INDEX IF NOT EXISTS idx_telegram_id ON usuarios(telegram_id)''')
        c.execute('''CREATE INDEX IF NOT EXISTS idx_usuario_pais ON usuarios(pais)''')
        c.execute('''CREATE INDEX IF NOT EXISTS idx_orden_usuario ON ordenes(usuario_id)''')
        c.execute('''CREATE INDEX IF NOT EXISTS idx_orden_estado ON ordenes(estado)''')
        c.execute('''CREATE INDEX IF NOT EXISTS idx_conversacion_usuario ON conversaciones(usuario_id)''')
        c.execute('''CREATE INDEX IF NOT EXISTS idx_auditoria_usuario ON auditoria(usuario_id)''')

        conn.commit()
        conn.close()
        logger.info("✅ Base de datos inicializada (WAL mode activo para multi-cuenta)")

    # ============= USUARIOS =============

    def crear_o_actualizar_usuario(self, telegram_id: int, nombre: str = "", 
                                   username: str = "", pais: str = None) -> Tuple[int, bool]:
        """
        Crea un usuario o lo actualiza si ya existe.
        Retorna (id_usuario, es_nuevo)
        """
        conn = sqlite3.connect(self.db_path, timeout=30)
        c = conn.cursor()

        try:
            # Intentar obtener usuario existente
            c.execute('SELECT id FROM usuarios WHERE telegram_id = ?', (telegram_id,))
            existente = c.fetchone()

            if existente:
                # Actualizar
                usuario_id = existente[0]
                c.execute('''UPDATE usuarios 
                           SET ultimo_mensaje = CURRENT_TIMESTAMP,
                               nombre = COALESCE(?, nombre),
                               username = COALESCE(?, username),
                               pais = COALESCE(?, pais)
                           WHERE id = ?''',
                         (nombre if nombre else None, 
                          username if username else None, 
                          pais, usuario_id))
                conn.commit()
                logger.info(f"ℹ️ Usuario actualizado: {nombre} ({telegram_id})")
                es_nuevo = False
            else:
                # Crear nuevo
                c.execute('''INSERT INTO usuarios 
                           (telegram_id, nombre, username, pais)
                           VALUES (?, ?, ?, ?)''',
                         (telegram_id, nombre, username, pais))
                conn.commit()
                usuario_id = c.lastrowid
                logger.info(f"✅ Usuario creado: {nombre} ({telegram_id})")
                es_nuevo = True

            return usuario_id, es_nuevo

        except Exception as e:
            logger.error(f"❌ Error en crear_o_actualizar_usuario: {e}")
            return None, False
        finally:
            conn.close()

    def obtener_usuario(self, telegram_id: int) -> Optional[Dict]:
        """Obtiene datos completos de un usuario"""
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        try:
            c.execute('''SELECT id, telegram_id, nombre, username, pais, moneda, 
                               creado, ultimo_mensaje
                        FROM usuarios WHERE telegram_id = ?''', (telegram_id,))
            usuario = c.fetchone()
            
            if usuario:
                return dict(usuario)
            return None
        finally:
            conn.close()

    def obtener_todos_usuarios(self, pais: str = None) -> List[Dict]:
        """Obtiene lista de usuarios, opcionalmente filtrados por país"""
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        try:
            if pais:
                c.execute('''SELECT id, telegram_id, nombre, username, pais, moneda, creado
                           FROM usuarios WHERE pais = ? ORDER BY creado DESC''', (pais,))
            else:
                c.execute('''SELECT id, telegram_id, nombre, username, pais, moneda, creado
                           FROM usuarios ORDER BY creado DESC''')
            
            return [dict(row) for row in c.fetchall()]
        finally:
            conn.close()

    # ============= DETECCIÓN DE PAÍS =============

    def registrar_deteccion_pais(self, usuario_id: int, pais: str, 
                                  metodo: str = "ia", confianza: float = 1.0):
        """Registra cómo se detectó el país de un usuario"""
        conn = sqlite3.connect(self.db_path, timeout=30)
        c = conn.cursor()

        try:
            c.execute('''INSERT INTO deteccion_pais 
                        (usuario_id, pais_detectado, metodo, confianza)
                        VALUES (?, ?, ?, ?)''',
                     (usuario_id, pais, metodo, confianza))
            
            # Actualizar país en usuarios
            c.execute('UPDATE usuarios SET pais = ? WHERE id = ?', (pais, usuario_id))
            
            conn.commit()
            logger.info(f"✅ País detectado para usuario {usuario_id}: {pais} ({confianza*100:.0f}%)")
        except Exception as e:
            logger.error(f"❌ Error registrando detección: {e}")
        finally:
            conn.close()

    # ============= PRECIOS =============

    def cargar_precios_desde_config(self, config: Dict):
        """Carga precios desde el archivo de configuración completo"""
        conn = sqlite3.connect(self.db_path, timeout=30)
        c = conn.cursor()

        try:
            if 'plantilla_precios' not in config or 'por_pais' not in config['plantilla_precios']:
                logger.warning("⚠️ Config no tiene estructura de precios")
                return

            plantilla = config['plantilla_precios']
            tasas = config.get('tasas_cambio', {})

            for pais, datos_pais in plantilla['por_pais'].items():
                # Obtener precios para cada producto
                for producto_id in ['11500_archivos', '36500_archivos', '86000_archivos']:
                    precio_regular = datos_pais.get('precios_regulares', {}).get(producto_id, 0)
                    precio_descuento = datos_pais.get('precios_descuento', {}).get(producto_id, 0)
                    
                    # Insertar o actualizar
                    c.execute('''INSERT OR REPLACE INTO precios_pais
                               (pais, moneda, producto_id, precio_regular, precio_descuento,
                                tasa_cambio, minimo_transferencia, confirmacion)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                             (pais, 
                              datos_pais.get('moneda', 'USD'),
                              producto_id,
                              precio_regular,
                              precio_descuento,
                              datos_pais.get('tasa', tasas.get(pais, 1)),
                              datos_pais.get('minimo', 0),
                              datos_pais.get('confirmacion', 'Inmediata')))

            conn.commit()
            logger.info(f"✅ Precios cargados en BD")
        except Exception as e:
            logger.error(f"❌ Error cargando precios: {e}")
        finally:
            conn.close()

    def obtener_precios_pais(self, pais: str) -> List[Dict]:
        """Obtiene todos los precios de un país"""
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        try:
            c.execute('''SELECT * FROM precios_pais WHERE pais = ?''', (pais,))
            return [dict(row) for row in c.fetchall()]
        finally:
            conn.close()

    # ============= MÉTODOS DE PAGO =============

    def guardar_metodos_pago(self, pais: str, metodos: List[str], datos_pago: Dict):
        """Guarda métodos de pago para un país"""
        conn = sqlite3.connect(self.db_path, timeout=30)
        c = conn.cursor()

        try:
            c.execute('''INSERT OR REPLACE INTO metodos_pago
                       (pais, metodos, datos_pago)
                       VALUES (?, ?, ?)''',
                     (pais, json.dumps(metodos), json.dumps(datos_pago)))
            conn.commit()
            logger.info(f"✅ Métodos de pago guardados para {pais}")
        except Exception as e:
            logger.error(f"❌ Error guardando métodos: {e}")
        finally:
            conn.close()

    def obtener_metodos_pago(self, pais: str) -> Optional[Dict]:
        """Obtiene métodos de pago de un país"""
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        try:
            c.execute('SELECT * FROM metodos_pago WHERE pais = ?', (pais,))
            row = c.fetchone()
            
            if row:
                return {
                    'pais': row['pais'],
                    'metodos': json.loads(row['metodos']),
                    'datos_pago': json.loads(row['datos_pago'])
                }
            return None
        finally:
            conn.close()

    # ============= ÓRDENES =============

    def crear_orden(self, usuario_id: int, producto_id: str, pais: str, 
                   moneda: str, precio_mostrado: float, precio_usd: float,
                   metodo_pago: str) -> Optional[int]:
        """Crea una nueva orden"""
        conn = sqlite3.connect(self.db_path, timeout=30)
        c = conn.cursor()

        try:
            c.execute('''INSERT INTO ordenes
                       (usuario_id, producto_id, pais, moneda, precio_mostrado, 
                        precio_usd, metodo_pago, estado)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 'pendiente')''',
                     (usuario_id, producto_id, pais, moneda, precio_mostrado, 
                      precio_usd, metodo_pago))
            conn.commit()
            orden_id = c.lastrowid
            logger.info(f"✅ Orden creada: {orden_id}")
            return orden_id
        except Exception as e:
            logger.error(f"❌ Error creando orden: {e}")
            return None
        finally:
            conn.close()

    def obtener_ordenes_usuario(self, usuario_id: int, estado: str = None) -> List[Dict]:
        """Obtiene órdenes de un usuario"""
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        try:
            if estado:
                c.execute('''SELECT * FROM ordenes 
                           WHERE usuario_id = ? AND estado = ?
                           ORDER BY creado DESC''', (usuario_id, estado))
            else:
                c.execute('''SELECT * FROM ordenes 
                           WHERE usuario_id = ?
                           ORDER BY creado DESC''', (usuario_id,))
            
            return [dict(row) for row in c.fetchall()]
        finally:
            conn.close()

    def actualizar_estado_orden(self, orden_id: int, nuevo_estado: str, referencia: str = None):
        """Actualiza el estado de una orden"""
        conn = sqlite3.connect(self.db_path, timeout=30)
        c = conn.cursor()

        try:
            if referencia:
                c.execute('''UPDATE ordenes 
                           SET estado = ?, referencia = ?, actualizado = CURRENT_TIMESTAMP
                           WHERE id = ?''', (nuevo_estado, referencia, orden_id))
            else:
                c.execute('''UPDATE ordenes 
                           SET estado = ?, actualizado = CURRENT_TIMESTAMP
                           WHERE id = ?''', (nuevo_estado, orden_id))
            conn.commit()
            logger.info(f"✅ Orden {orden_id} → {nuevo_estado}")
        except Exception as e:
            logger.error(f"❌ Error actualizando orden: {e}")
        finally:
            conn.close()

    # ============= CONVERSACIONES =============

    def guardar_conversacion(self, usuario_id: int, mensaje_usuario: str,
                            respuesta_bot: str, pais_detectado: str = None,
                            tokens_usados: int = 0, cuenta_sesion: str = None):
        """Guarda una conversación completa"""
        conn = sqlite3.connect(self.db_path, timeout=30)
        c = conn.cursor()

        try:
            c.execute('''INSERT INTO conversaciones
                       (usuario_id, mensaje_usuario, respuesta_bot, pais_detectado, cuenta_sesion, tokens_usados)
                       VALUES (?, ?, ?, ?, ?, ?)''',
                     (usuario_id, mensaje_usuario[:1000], respuesta_bot[:2000],
                      pais_detectado, cuenta_sesion, tokens_usados))
            conn.commit()
            logger.info(f"✅ Conversación guardada (usuario {usuario_id} | sesion {cuenta_sesion})")
        except Exception as e:
            logger.error(f"❌ Error guardando conversación: {e}")
        finally:
            conn.close()

    def obtener_historial_usuario(self, usuario_id: int, limite: int = 10) -> List[Dict]:
        """Obtiene historial de conversaciones de un usuario"""
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        try:
            c.execute('''SELECT * FROM conversaciones
                       WHERE usuario_id = ?
                       ORDER BY timestamp DESC
                       LIMIT ?''', (usuario_id, limite))
            
            return [dict(row) for row in reversed(c.fetchall())]
        finally:
            conn.close()

    # ============= PLANTILLAS =============

    def guardar_plantilla_enviada(self, usuario_id: int, plantilla_tipo: str, 
                                 pais: str, contenido: Dict):
        """Registra una plantilla que se envió a un usuario"""
        conn = sqlite3.connect(self.db_path, timeout=30)
        c = conn.cursor()

        try:
            c.execute('''INSERT INTO plantillas_enviadas
                       (usuario_id, plantilla_tipo, pais, contenido)
                       VALUES (?, ?, ?, ?)''',
                     (usuario_id, plantilla_tipo, pais, json.dumps(contenido)))
            conn.commit()
        except Exception as e:
            logger.error(f"❌ Error guardando plantilla: {e}")
        finally:
            conn.close()

    # ============= AUDITORÍA =============

    def registrar_auditoria(self, usuario_id: int, accion: str, detalles: Dict = None, ip: str = None):
        """Registra una acción para auditoría"""
        conn = sqlite3.connect(self.db_path, timeout=30)
        c = conn.cursor()

        try:
            c.execute('''INSERT INTO auditoria
                       (usuario_id, accion, detalles, ip)
                       VALUES (?, ?, ?, ?)''',
                     (usuario_id, accion, json.dumps(detalles or {}), ip))
            conn.commit()
        except Exception as e:
            logger.error(f"❌ Error en auditoría: {e}")
        finally:
            conn.close()

    # ============= ESTADÍSTICAS =============

    def obtener_estadisticas(self) -> Dict:
        """Obtiene estadísticas generales del sistema"""
        conn = sqlite3.connect(self.db_path, timeout=30)
        c = conn.cursor()

        try:
            stats = {}

            # Usuarios
            c.execute('SELECT COUNT(*) FROM usuarios')
            stats['total_usuarios'] = c.fetchone()[0]

            c.execute('SELECT COUNT(DISTINCT pais) FROM usuarios WHERE pais IS NOT NULL')
            stats['paises_activos'] = c.fetchone()[0]

            # Órdenes
            c.execute('SELECT COUNT(*) FROM ordenes')
            stats['total_ordenes'] = c.fetchone()[0]

            c.execute('SELECT COUNT(*) FROM ordenes WHERE estado = "pagada"')
            stats['ordenes_pagadas'] = c.fetchone()[0]

            c.execute('SELECT COUNT(*) FROM ordenes WHERE estado = "pendiente"')
            stats['ordenes_pendientes'] = c.fetchone()[0]

            # Ventas
            c.execute('SELECT SUM(precio_usd) FROM ordenes WHERE estado = "pagada"')
            stats['ventas_total_usd'] = c.fetchone()[0] or 0

            # Por país
            c.execute('''SELECT pais, COUNT(*) as count, SUM(precio_mostrado) as total
                        FROM ordenes WHERE estado = "pagada"
                        GROUP BY pais ORDER BY total DESC''')
            stats['ventas_por_pais'] = {row[0]: {'órdenes': row[1], 'total': row[2]} 
                                        for row in c.fetchall()}

            # Conversaciones
            c.execute('SELECT COUNT(*) FROM conversaciones')
            stats['total_conversaciones'] = c.fetchone()[0]

            return stats
        finally:
            conn.close()

    def obtener_usuario_por_pais(self, pais: str) -> int:
        """Obtiene cantidad de usuarios por país"""
        conn = sqlite3.connect(self.db_path, timeout=30)
        c = conn.cursor()

        try:
            c.execute('SELECT COUNT(*) FROM usuarios WHERE pais = ?', (pais,))
            return c.fetchone()[0]
        finally:
            conn.close()

    def obtener_paises_activos(self) -> List[str]:
        """Obtiene lista de países con usuarios activos"""
        conn = sqlite3.connect(self.db_path, timeout=30)
        c = conn.cursor()

        try:
            c.execute('SELECT DISTINCT pais FROM usuarios WHERE pais IS NOT NULL ORDER BY pais')
            return [row[0] for row in c.fetchall()]
        finally:
            conn.close()

    def registrar_imagen_reenviada(self, telegram_id: int):
        """Incrementa el contador de imágenes reenviadas para un usuario"""
        conn = sqlite3.connect(self.db_path, timeout=30)
        c = conn.cursor()
        try:
            # Agregar columna si no existe (migración segura)
            try:
                c.execute('ALTER TABLE usuarios ADD COLUMN imagenes_enviadas INTEGER DEFAULT 0')
                conn.commit()
            except Exception:
                pass  # La columna ya existe

            c.execute('''UPDATE usuarios SET imagenes_enviadas = COALESCE(imagenes_enviadas, 0) + 1
                        WHERE telegram_id = ?''', (telegram_id,))
            conn.commit()
        except Exception as e:
            logger.error(f"Error registrando imagen: {e}")
        finally:
            conn.close()

    def obtener_estadisticas_simples(self) -> dict:
        """Estadísticas simplificadas: solo usuarios e imágenes"""
        conn = sqlite3.connect(self.db_path, timeout=30)
        c = conn.cursor()
        try:
            c.execute('SELECT COUNT(*) FROM usuarios')
            total_usuarios = c.fetchone()[0]

            try:
                c.execute('SELECT COALESCE(SUM(imagenes_enviadas), 0) FROM usuarios')
                total_imagenes = c.fetchone()[0]
            except Exception:
                total_imagenes = 0

            return {
                'total_usuarios': total_usuarios,
                'total_imagenes_reenviadas': total_imagenes
            }
        finally:
            conn.close()


# Funciones de utilidad global
def inicializar_bd(ruta: str = 'userbot_completo.db') -> DatabaseManager:
    """Inicializa la base de datos"""
    return DatabaseManager(ruta)


if __name__ == "__main__":
    # Test básico
    logging.basicConfig(level=logging.INFO)
    
    db = DatabaseManager()
    
    # Crear usuario de prueba
    usuario_id, es_nuevo = db.crear_o_actualizar_usuario(
        telegram_id=123456789,
        nombre="Usuario Test",
        username="user_test",
        pais="Argentina"
    )
    
    # Obtener estadísticas
    stats = db.obtener_estadisticas()
    print("\n📊 ESTADÍSTICAS:")
    print(f"  Total usuarios: {stats['total_usuarios']}")
    print(f"  Países activos: {stats['paises_activos']}")
    print(f"  Total órdenes: {stats['total_ordenes']}")
