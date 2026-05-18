import os
import datetime
import requests
import functions_framework
from google.cloud import bigquery

# Inicializar el cliente de BigQuery de forma global para reutilizar conexiones
bq_client = bigquery.Client()

# Configuración fija de tu infraestructura en GCP
PROJECT_ID = "gcp-data-portfolio-cll"
DATASET_ID = "flights_data_silver"
TABLE_ID = "raw_flight_offers"  # ✅ Nombre correcto de tu tabla

@functions_framework.http
def ingest_flight_data(request):
    """Cloud Function para ingestar datos de vuelos desde la API de Kiwi Tequila hacia BigQuery."""
    
    # ==========================================
    # 1. EXTRACCIÓN Y VALIDACIÓN DE PARÁMETROS
    # ==========================================
    try:
        request_json = request.get_json(silent=True) or {}
    except Exception:
        request_json = {}

    # Captura de parámetros tanto de la URL (GET) como del Body (POST)
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

    print(f"🛫 Iniciando búsqueda: {origin} -> {destination} ({days_advance} días de avance, {adults} adultos, max {max_results} resultados).")

    # ==========================================
    # 2. VERIFICACIÓN DE CREDENCIALES
    # ==========================================
    # Lee la clave secreta desde las variables de entorno (inyectada de forma segura desde Secret Manager)
    kiwi_api_key = os.environ.get("KIWI_API_KEY") or os.environ.get("AMADEUS_CLIENT_SECRET")
    
    if not kiwi_api_key:
        print("❌ Error de configuración: Falta la API Key en las variables de entorno.")
        return {
            "status": "error", 
            "message": "Falta la configuración de autenticación en el servidor (KIWI_API_KEY)."
        }, 500

    # ==========================================
    # 3. CÁLCULO DE FECHAS (Formato Kiwi: DD/MM/YYYY)
    # ==========================================
    target_date = datetime.date.today() + datetime.timedelta(days=days_advance)
    date_str = target_date.strftime("%d/%m/%Y")

    # ==========================================
    # 4. PETICIÓN HTTP Y MANEJO DE EXCEPCIONES INTERNAS
    # ==========================================
    kiwi_url = "https://api.tequila.kiwi.com/v2/search"
    
    headers = {
        "apikey": kiwi_api_key,
        "accept": "application/json"
    }
    
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
        
        # Si la API responde pero devuelve un código de error (400, 401, 429, 500...)
        if response.status_code != 200:
            try:
                error_json = response.json()
                motivo_interno = error_json.get("message") or error_json.get("error") or error_json
            except Exception:
                motivo_interno = response.text[:500]

            print(f"❌ La API de Kiwi devolvió un Error {response.status_code}: {motivo_interno}")
            return {
                "status": "error",
                "message": f"Fallo en el proveedor externo (Kiwi Status {response.status_code}).",
                "motivo_interno": motivo_interno
            }, response.status_code
            
        data = response.json()
        
    except requests.exceptions.Timeout:
        print("❌ Error: Tiempo de espera agotado al conectar con Kiwi (Timeout).")
        return {
            "status": "error", 
            "message": "El proveedor de vuelos tardó demasiado en responder (Timeout)."
        }, 504
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Error de red/conexión: {str(e)}")
        return {
            "status": "error", 
            "message": "No se pudo establecer conexión con el servicio de Kiwi.", 
            "motivo_interno": str(e)
        }, 500
        
    except Exception as e:
        print(f"❌ Excepción inesperada: {str(e)}")
        return {
            "status": "error", 
            "message": "Error interno imprevisto en la ejecución del script.", 
            "motivo_interno": str(e)
        }, 500

    # ==========================================
    # 5. ESTRUCTURACIÓN DE DATOS (MAPPING)
    # ==========================================
    flights_to_insert = []
    
    for flight in data.get("data", []):
        try:
            flight_row = {
                "fecha_ingesta": datetime.datetime.utcnow().isoformat(),
                "origen": origin,
                "destino": destination,
                "fecha_vuelo": target_date.isoformat(),
                "aerolinea": flight.get("airlines", ["Desconocido"])[0],
                "precio": float(flight.get("price", 0.0)),
                "escala": len(flight.get("route", [])) - 1,
                "vuelo_num": str(flight.get("route", [{}])[0].get("flight_no", ""))
            }
            flights_to_insert.append(flight_row)
        except Exception as parse_err:
            print(f"⚠️ Saltando un registro de vuelo por error de formato: {str(parse_err)}")
            continue

    # ==========================================
    # 6. INSERCIÓN EN BIGQUERY
    # ==========================================
    if flights_to_insert:
        table_ref = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"
        print(f"📥 Insertando {len(flights_to_insert)} registros en BigQuery: {table_ref}")
        
        try:
            errors = bq_client.insert_rows_json(table_ref, flights_to_insert)
            
            if errors == []:
                print("✅ Inserción completada con éxito en BigQuery.")
                return {
                    "status": "success",
                    "message": f"Se han guardado {len(flights_to_insert)} vuelos correctamente en {TABLE_ID}."
                }, 200
            else:
                print(f"❌ Error de streaming en BigQuery: {errors}")
                return {
                    "status": "error",
                    "message": "Los datos se recibieron de Kiwi pero BigQuery rechazó las filas.",
                    "motivo_interno": errors
                }, 500
                
        except Exception as bq_err:
            print(f"❌ Error crítico al conectar o insertar en BigQuery: {str(bq_err)}")
            return {
                "status": "error",
                "message": "La función colapsó al intentar escribir en BigQuery. Revisa el esquema o permisos.",
                "motivo_interno": str(bq_err)
            }, 500
    else:
        print("🛈 No se encontró ningún vuelo que coincida con los criterios.")
        return {
            "status": "success",
            "message": "Búsqueda finalizada sin resultados. No se añadieron filas a BigQuery."
        }, 200