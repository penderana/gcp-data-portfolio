import functions_framework
import requests
import datetime
import os
from google.cloud import bigquery

# Configuramos variables que vendrán del entorno (Terraform)
PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
AMADEUS_CLIENT_ID = os.environ.get("AMADEUS_CLIENT_ID")
AMADEUS_CLIENT_SECRET = os.environ.get("AMADEUS_CLIENT_SECRET")
DATASET_ID = "flights_data"
TABLE_ID = "flight_offers_raw"

def get_amadeus_token():
    auth_url = "https://test.api.amadeus.com/v1/security/oauth2/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "client_credentials",
        "client_id": AMADEUS_CLIENT_ID,
        "client_secret": AMADEUS_CLIENT_SECRET
    }
    response = requests.post(auth_url, headers=headers, data=data)
    response.raise_for_status()
    return response.json()["access_token"]

@functions_framework.http
def ingest_flight_data(request):
    try:
        # 1. Autenticación (Obtener Token)
        token = get_amadeus_token()
        
        # 2. Buscar vuelos (Ej: MAD -> TYO para dentro de 1 mes)
        # Calculamos fecha dinámica: hoy + 30 días
        travel_date = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()
        
        search_url = "https://test.api.amadeus.com/v2/shopping/flight-offers"
        headers = {"Authorization": f"Bearer {token}"}
        params = {
            "originLocationCode": "MAD",
            "destinationLocationCode": "TYO",
            "departureDate": travel_date,
            "adults": 1,
            "max": 5 # Solo traemos 5 ofertas para no llenar BQ en pruebas
        }
        
        response = requests.get(search_url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        
        # 3. Guardar en BigQuery
        client = bigquery.Client(project=PROJECT_ID)
        timestamp = datetime.datetime.utcnow().isoformat()
        
        # Guardamos la respuesta completa como un solo registro JSON
        rows_to_insert = [{
            "ingestion_timestamp": timestamp,
            "data_payload": str(data) 
        }]
        
        table_ref = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"
        errors = client.insert_rows_json(table_ref, rows_to_insert)
        
        if errors == []:
            return f"Vuelos MAD-TYO ingesta OK. Fecha viaje: {travel_date}", 200
        else:
            return f"Error en BQ: {errors}", 500

    except Exception as e:
        return f"Error crítico: {str(e)}", 500