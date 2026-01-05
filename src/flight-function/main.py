import functions_framework
import requests
import datetime
import os
import json
import logging
from google.cloud import bigquery
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuración desde variables de entorno
PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
AMADEUS_CLIENT_ID = os.environ.get("AMADEUS_CLIENT_ID")
AMADEUS_CLIENT_SECRET = os.environ.get("AMADEUS_CLIENT_SECRET")
AMADEUS_ENV = os.environ.get("AMADEUS_ENV", "test")  # test o production
DATASET_ID = os.environ.get("DATASET_ID", "flights_data")
TABLE_ID = os.environ.get("TABLE_ID", "raw_flight_offers")
MAX_OFFERS = int(os.environ.get("MAX_OFFERS", "10"))
DAYS_IN_ADVANCE = int(os.environ.get("DAYS_IN_ADVANCE", "30"))

# URL base según entorno
AMADEUS_BASE_URL = (
    "https://api.amadeus.com" if AMADEUS_ENV == "production" 
    else "https://test.api.amadeus.com"
)

def validate_environment():
    """Valida que todas las variables de entorno requeridas estén presentes"""
    required_vars = {
        "GCP_PROJECT_ID": PROJECT_ID,
        "AMADEUS_CLIENT_ID": AMADEUS_CLIENT_ID,
        "AMADEUS_CLIENT_SECRET": AMADEUS_CLIENT_SECRET
    }
    
    missing = [var for var, value in required_vars.items() if not value]
    
    if missing:
        raise ValueError(f"Faltan variables de entorno requeridas: {', '.join(missing)}")
    
    logger.info(f"Configuración validada. Entorno: {AMADEUS_ENV}, Max ofertas: {MAX_OFFERS}")

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(requests.exceptions.RequestException)
)
def get_amadeus_token():
    """Obtiene token de autenticación de Amadeus con retry automático"""
    auth_url = f"{AMADEUS_BASE_URL}/v1/security/oauth2/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "client_credentials",
        "client_id": AMADEUS_CLIENT_ID,
        "client_secret": AMADEUS_CLIENT_SECRET
    }
    
    try:
        logger.info("Solicitando token de Amadeus...")
        response = requests.post(auth_url, headers=headers, data=data, timeout=10)
        response.raise_for_status()
        logger.info("Token obtenido exitosamente")
        return response.json()["access_token"]
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            logger.error("Error de autenticación: credenciales inválidas")
            raise ValueError("Credenciales de Amadeus inválidas")
        elif e.response.status_code == 403:
            logger.error("Acceso denegado por Amadeus")
            raise ValueError("Acceso denegado a la API de Amadeus")
        else:
            logger.error(f"Error HTTP al obtener token: {e}")
            raise
    except requests.exceptions.Timeout:
        logger.error("Timeout al solicitar token")
        raise
    except Exception as e:
        logger.error(f"Error inesperado al obtener token: {str(e)}")
        raise

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(requests.exceptions.RequestException)
)
def search_flights(token, origin, destination, departure_date, adults, max_results):
    """Busca ofertas de vuelos en Amadeus con retry automático"""
    search_url = f"{AMADEUS_BASE_URL}/v2/shopping/flight-offers"
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "originLocationCode": origin,
        "destinationLocationCode": destination,
        "departureDate": departure_date,
        "adults": adults,
        "max": max_results
    }
    
    try:
        logger.info(f"Buscando vuelos: {origin} → {destination} para {departure_date} ({adults} adulto(s))")
        response = requests.get(search_url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        num_offers = len(data.get("data", []))
        logger.info(f"Búsqueda exitosa: {num_offers} ofertas encontradas")
        
        return data
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 400:
            logger.error(f"Parámetros de búsqueda inválidos: {e.response.text}")
            raise ValueError(f"Parámetros inválidos: {e.response.text}")
        elif e.response.status_code == 404:
            logger.warning("No se encontraron vuelos para los criterios especificados")
            return {"data": [], "meta": {"count": 0}}
        else:
            logger.error(f"Error HTTP en búsqueda de vuelos: {e}")
            raise
    except requests.exceptions.Timeout:
        logger.error("Timeout en búsqueda de vuelos")
        raise
    except Exception as e:
        logger.error(f"Error inesperado en búsqueda: {str(e)}")
        raise

def insert_to_bigquery(data, origin, destination, departure_date, search_params):
    """Inserta datos en BigQuery"""
    try:
        client = bigquery.Client(project=PROJECT_ID)
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        # Extraemos información relevante para columnas dedicadas
        num_offers = len(data.get("data", []))
        
        # Estructura mejorada del registro
        row = {
            "ingestion_timestamp": timestamp,
            "origin": origin,
            "destination": destination,
            "departure_date": departure_date,
            "num_offers": num_offers,
            "adults": search_params.get("adults", 1),
            "search_params": json.dumps(search_params),
            "data_payload": json.dumps(data),  # ✅ JSON válido
            "amadeus_env": AMADEUS_ENV
        }
        
        table_ref = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"
        logger.info(f"Insertando en BigQuery: {table_ref}")
        
        errors = client.insert_rows_json(table_ref, [row])
        
        if errors:
            logger.error(f"Errores en BigQuery: {errors}")
            raise Exception(f"Error al insertar en BigQuery: {errors}")
        
        logger.info(f"Datos insertados exitosamente en BigQuery ({num_offers} ofertas)")
        return True
        
    except Exception as e:
        logger.error(f"Error al insertar en BigQuery: {str(e)}")
        raise

@functions_framework.http
def ingest_flight_data(request):
    """
    Cloud Function principal para ingesta de datos de vuelos.
    
    Parámetros del request (Query params o JSON body):
    - origin: Código IATA de origen (default: MAD)
    - destination: Código IATA de destino (default: TYO)
    - days_advance: Días en el futuro para la búsqueda (default: 30)
    - adults: Número de adultos (default: 1)
    - max_results: Máximo de ofertas a traer (default: valor de MAX_OFFERS env var)
    
    Ejemplo: ?origin=BCN&destination=NYC&days_advance=45&adults=2
    """
    
    try:
        # Validar configuración
        validate_environment()
        
        # Obtener parámetros del request (soporta GET y POST)
        request_json = request.get_json(silent=True) or {}
        
        origin = request.args.get("origin") or request_json.get("origin", "MAD")
        destination = request.args.get("destination") or request_json.get("destination", "TYO")
        days_advance = int(request.args.get("days_advance") or request_json.get("days_advance", DAYS_IN_ADVANCE))
        adults = int(request.args.get("adults") or request_json.get("adults", 1))
        max_results = int(request.args.get("max_results") or request_json.get("max_results", MAX_OFFERS))
        
        # Validaciones básicas
        if len(origin) != 3 or len(destination) != 3:
            return {"error": "Los códigos IATA deben tener 3 caracteres"}, 400
        
        if adults < 1 or adults > 9:
            return {"error": "El número de adultos debe estar entre 1 y 9"}, 400
        
        if days_advance < 1:
            return {"error": "days_advance debe ser al menos 1"}, 400
        
        # Calcular fecha de viaje
        departure_date = (datetime.date.today() + datetime.timedelta(days=days_advance)).isoformat()
        
        # 1. Autenticación
        token = get_amadeus_token()
        
        # 2. Buscar vuelos
        search_params = {
            "origin": origin,
            "destination": destination,
            "departure_date": departure_date,
            "adults": adults,
            "max_results": max_results
        }
        
        flight_data = search_flights(
            token=token,
            origin=origin.upper(),
            destination=destination.upper(),
            departure_date=departure_date,
            adults=adults,
            max_results=max_results
        )
        
        # 3. Guardar en BigQuery
        insert_to_bigquery(flight_data, origin.upper(), destination.upper(), departure_date, search_params)
        
        # Respuesta exitosa
        num_offers = len(flight_data.get("data", []))
        response = {
            "status": "success",
            "message": f"Ingesta completada exitosamente",
            "details": {
                "origin": origin.upper(),
                "destination": destination.upper(),
                "departure_date": departure_date,
                "offers_found": num_offers,
                "amadeus_env": AMADEUS_ENV
            }
        }
        
        logger.info(f"Proceso completado: {num_offers} ofertas ingresadas")
        return response, 200
        
    except ValueError as e:
        logger.error(f"Error de validación: {str(e)}")
        return {"error": str(e)}, 400
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error de red/API: {str(e)}")
        return {"error": f"Error al comunicarse con Amadeus: {str(e)}"}, 502
        
    except Exception as e:
        logger.error(f"Error crítico: {str(e)}", exc_info=True)
        return {"error": f"Error interno: {str(e)}"}, 500