import os
import json  # ✅ Añadido para serializar los campos JSON correctamente
import datetime
import requests
import functions_framework
from google.cloud import bigquery

# Inicializar el cliente de BigQuery de forma global
bq_client = bigquery.Client()

# Configuración estricta basada en tu infraestructura
PROJECT_ID = "gcp-data-portfolio-cll"
DATASET_ID = "flights_data"
TABLE_ID = "raw_flight_offers"

@functions_framework.http
def ingest_flight_data(request):
    """Cloud Function adaptada exactamente al esquema de la tabla raw_flight_offers."""
    
    # ==========================================
    # 1. EXTRACCIÓN Y VALIDACIÓN DE PARÁMETROS
    # ==========================================
    try:
        request_json = request.get_json(silent=True) or {}
    except Exception:
        request_json = {}

    origin = request.args.get("origin") or request_json.get("origin") or "MAD"
    destination = request.args.get("destination") or request_json.get("destination") or "BCN"
    
    try:
        days_advance = int(request.args.get("days_advance") or request_json.get("days_advance") or 15)
    except (ValueError, TypeError):
        days_advance = 15
        
    try:
        adults = int(request.args.get("adults") or request_json.get("adults") or 1)
    except (ValueError, TypeError):
        adults = 1
        
    try:
        max_results = int(request.args.get("max_results") or request_json.get("max_results") or 5)
    except (ValueError, TypeError):
        max_results = 5

    print(f"🛫 Buscando: {origin} -> {destination} ({days_advance} días de avance).")

    # ==========================================
    # 2. VERIFICACIÓN DE CREDENCIALES (SECRET MANAGER)
    # ==========================================
    kiwi_api_key = os.environ.get("KIWI_API_KEY")
    
    if not kiwi_api_key:
        print("❌ Error: La variable KIWI_API_KEY no está configurada.")
        return {"status": "error", "message": "Falta la API Key en el servidor."}, 500

    # ==========================================
    # 3. CÁLCULO DE FECHAS
    # ==========================================
    target_date = datetime.date.today() + datetime.timedelta(days=days_advance)
    date_str = target_date.strftime("%d/%m/%Y")

    # ==========================================
    # 4. PETICIÓN HTTP A KIWI TEQUILA
    # ==========================================
    kiwi_url = "https://api.tequila.kiwi.com/v2/search"
    headers = {"apikey": kiwi_api_key, "accept": "application/json"}
    query_params = {
        "fly_from": origin,
        "fly_to": destination,
        "date_from": date_str,
        "date_to": date_str,
        "adults": adults,
        "curr": "EUR",
        "limit": max_results,
        "flight_type": "oneway"
    }

    try:
        response = requests.get(kiwi_url, headers=headers, params=query_params, timeout=12)
        
        if response.status_code != 200:
            try:
                motivo_interno = response.json().get("message") or response.json()
            except Exception:
                motivo_interno = response.text[:500]
            return {
                "status": "error",
                "message": f"Kiwi denegó el acceso (Status {response.status_code}).",
                "motivo_interno": motivo_interno
            }, response.status_code
            
        data = response.json()
        
    except Exception as e:
        return {"status": "error", "message": "Fallo de conexión con el proveedor.", "motivo_interno": str(e)}, 500

    # ==========================================
    # 5. MAPEADO EXACTO AL ESQUEMA DE TU CAPTURA
    # ==========================================
    offers_list = data.get("data", [])
    
    # Preparamos el bloque de metadatos de búsqueda
    search_metadata = {
        "days_advance": days_advance,
        "max_results": max_results,
        "api_provider": "kiwi_tequila"
    }

    # Creamos la fila aplicando json.dumps() a las columnas de tipo JSON
    flight_row = {
        "ingestion_timestamp": datetime.datetime.utcnow().isoformat(),  # TIMESTAMP
        "origin": origin,                                              # STRING
        "destination": destination,                                    # STRING
        "departure_date": target_date.isoformat(),                     # DATE
        "num_offers": len(offers_list),                                # INTEGER
        "adults": adults,                                              # INTEGER
        "search_params": json.dumps(search_metadata),                  # ✅ CORREGIDO: Enviado como String JSON
        "data_payload": json.dumps(data),                              # ✅ CORREGIDO: Enviado como String JSON
        "amadeus_env": "kiwi_tequila_migration"                         # STRING
    }

    # ==========================================
    # 6. INSERCIÓN EN BIGQUERY
    # ==========================================
    table_ref = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"
    
    try:
        errors = bq_client.insert_rows_json(table_ref, [flight_row])
        
        if errors == []:
            print("✅ Datos guardados con éxito en la tabla raw_flight_offers.")
            return {
                "status": "success",
                "message": f"Se ha insertado la consulta con {len(offers_list)} ofertas en BigQuery."
            }, 200
        else:
            print(f"❌ BigQuery rechazó las filas: {errors}")
            return {"status": "error", "message": "Rechazo de esquema en BigQuery.", "motivo_interno": errors}, 500
            
    except Exception as bq_err:
        print(f"❌ Error crítico en BigQuery: {str(bq_err)}")
        return {"status": "error", "message": "Fallo crítico al escribir en la tabla.", "motivo_interno": str(bq_err)}, 500