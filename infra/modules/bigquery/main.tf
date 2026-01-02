# 1. El Dataset 
resource "google_bigquery_dataset" "flights" {
  dataset_id                  = "flights_data"
  friendly_name               = "Flights Data"
  description                 = "Dataset para almacenar ingestas de APIs externas (Vuelos)"
  location                    = "EUROPE-SOUTHWEST1" # Madrid
  
  # Importante para pruebas: permite borrar el dataset aunque tenga tablas dentro
  delete_contents_on_destroy = true 
}

# 2. La Tabla 
resource "google_bigquery_table" "raw_flight_offers_table" {
  # Referencia dinámica: Usa el ID del dataset que creamos arriba
  dataset_id = google_bigquery_dataset.flights.dataset_id
  table_id   = "raw_flight_offers"

  # Particionamiento por día (Optimización de costes)
  time_partitioning {
    type  = "DAY"
    field = "ingestion_timestamp"
  }

  labels = {
    env = "production"
    app = "flight-tracker"
  }

  # Esquema (Columnas)
  schema = <<EOF
[
  {
    "name": "ingestion_timestamp",
    "type": "TIMESTAMP",
    "mode": "REQUIRED",
    "description": "Fecha y hora de cuando pedimos el dato a Amadeus"
  },
  {
    "name": "data_payload",
    "type": "JSON",
    "mode": "NULLABLE",
    "description": "Respuesta cruda de la API con las ofertas de vuelo"
  }
]
EOF
}