import os
import time
import json
import random
from datetime import datetime
from faker import Faker
from google.cloud import pubsub_v1
from concurrent.futures import TimeoutError

# ============================================================================
# CONFIGURACIÓN
# ============================================================================
PROJECT_ID = os.getenv("GCP_PROJECT_ID", "gcp-data-portfolio-cll")
TOPIC_ID = os.getenv("PUBSUB_TOPIC", "transactions-topic")
SLEEP_INTERVAL = float(os.getenv("SLEEP_INTERVAL", "0.5"))
PUBLISH_TIMEOUT = 5  # segundos para esperar confirmación

# ============================================================================
# INICIALIZACIÓN
# ============================================================================
publisher = pubsub_v1.PublisherClient()
topic_path = publisher.topic_path(PROJECT_ID, TOPIC_ID)
fake = Faker()

# Contadores para estadísticas
stats = {
    "sent": 0,
    "failed": 0,
    "start_time": time.time()
}

print("=" * 70)
print(f"🚀 Generador de Transacciones Falsas para Google Pub/Sub")
print("=" * 70)
print(f"📍 Project ID: {PROJECT_ID}")
print(f"📢 Topic: {TOPIC_ID}")
print(f"⏱️  Intervalo: {SLEEP_INTERVAL}s entre mensajes")
print(f"🔗 Topic Path: {topic_path}")
print("=" * 70)
print("Presiona Ctrl+C para detener\n")

# ============================================================================
# FUNCIONES
# ============================================================================

def generate_transaction():
    """
    Genera una transacción bancaria falsa con datos realistas.
    
    Returns:
        dict: Diccionario con datos de la transacción
    """
    return {
        "transaction_id": fake.uuid4(),
        "timestamp": datetime.utcnow().isoformat() + "Z",  # Formato ISO 8601
        "user_id": random.randint(1, 1000),
        "user_name": fake.name(),
        "amount": round(random.uniform(10.0, 5000.0), 2),
        "currency": random.choice(["USD", "EUR", "GBP"]),
        "merchant_id": random.randint(1, 50),
        "merchant_name": fake.company(),
        "transaction_type": random.choice(["purchase", "withdrawal", "transfer"]),
        "status": random.choice(["completed", "pending", "failed"]),
        "location": {
            "city": fake.city(),
            "country": fake.country_code()
        }
    }

def publish_message(data):
    """
    Publica un mensaje a Pub/Sub con manejo de errores.
    
    Args:
        data (dict): Datos a publicar
        
    Returns:
        str: Message ID si tiene éxito, None si falla
    """
    try:
        # Serializar a JSON y convertir a bytes
        message_bytes = json.dumps(data).encode("utf-8")
        
        # Publicar (retorna un Future)
        future = publisher.publish(topic_path, message_bytes)
        
        # Esperar confirmación con timeout
        message_id = future.result(timeout=PUBLISH_TIMEOUT)
        
        return message_id
        
    except TimeoutError:
        print(f"⏱️  TIMEOUT: No se recibió confirmación en {PUBLISH_TIMEOUT}s")
        return None
    except Exception as e:
        print(f"❌ ERROR publicando: {type(e).__name__}: {e}")
        return None

def print_stats():
    """Imprime estadísticas de ejecución."""
    elapsed = time.time() - stats["start_time"]
    rate = stats["sent"] / elapsed if elapsed > 0 else 0
    
    print("\n" + "=" * 70)
    print("📊 ESTADÍSTICAS FINALES")
    print("=" * 70)
    print(f"✅ Mensajes enviados: {stats['sent']}")
    print(f"❌ Mensajes fallidos: {stats['failed']}")
    print(f"⏱️  Tiempo total: {elapsed:.2f}s")
    print(f"📈 Tasa promedio: {rate:.2f} msg/s")
    print("=" * 70)

# ============================================================================
# BUCLE PRINCIPAL
# ============================================================================

try:
    while True:
        # Generar transacción
        data = generate_transaction()
        
        # Publicar mensaje
        message_id = publish_message(data)
        
        if message_id:
            stats["sent"] += 1
            print(f"[{stats['sent']}] ✓ {data['amount']} {data['currency']} "
                  f"| {data['transaction_type']} | ID: {message_id[:8]}...")
        else:
            stats["failed"] += 1
            print(f"[FAIL] ✗ No se pudo enviar transacción")
        
        # Simular tráfico
        time.sleep(SLEEP_INTERVAL)

except KeyboardInterrupt:
    print("\n\n🛑 Deteniendo generador...")
    print_stats()
    print("\n👋 ¡Hasta luego!")

except Exception as e:
    print(f"\n💥 ERROR FATAL: {type(e).__name__}: {e}")
    print_stats()
    raise