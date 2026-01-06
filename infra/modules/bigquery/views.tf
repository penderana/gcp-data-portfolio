# infra/modules/bigquery/views.tf

resource "google_bigquery_dataset" "silver" {
  dataset_id    = "flights_data"
  friendly_name = "Silver Layer - Cleaned Data"
  description   = "Datos limpios y transformados de la capa raw"
  location      = var.location
  project       = var.project_id
  
  labels = {
    env   = "production"
    layer = "silver"
  }
}

resource "google_bigquery_table" "flight_offers_clean_view" {
  dataset_id = google_bigquery_dataset.silver.dataset_id
  table_id   = "flight_offers_clean"
  project    = var.project_id
  
  deletion_protection = false
  
  view {
    query = <<-SQL
      -- Vista Silver: Limpieza y transformación de datos raw de vuelos
      WITH cleaned_data AS (
        SELECT
          -- Timestamp convertido a hora española (CET/CEST)
          DATETIME(ingestion_timestamp, 'Europe/Madrid') AS ingestion_datetime_es,
          ingestion_timestamp AS ingestion_timestamp_utc,
          
          -- Información de búsqueda - limpieza de códigos IATA
          UPPER(TRIM(COALESCE(origin, 'UNKNOWN'))) AS origin,
          UPPER(TRIM(COALESCE(destination, 'UNKNOWN'))) AS destination,
          
          -- Fecha de salida con validación
          CASE 
            WHEN departure_date IS NULL THEN NULL
            WHEN departure_date < CURRENT_DATE() THEN NULL
            ELSE departure_date
          END AS departure_date,
          
          -- Número de ofertas con validación
          CASE 
            WHEN num_offers IS NULL THEN 0
            WHEN num_offers < 0 THEN 0
            ELSE num_offers
          END AS num_offers,
          
          -- Número de adultos con validación
          CASE 
            WHEN adults IS NULL THEN 1
            WHEN adults < 1 THEN 1
            WHEN adults > 9 THEN 9
            ELSE adults
          END AS adults,
          
          -- Entorno Amadeus normalizado
          UPPER(COALESCE(amadeus_env, 'UNKNOWN')) AS amadeus_env,
          
          -- Flags de calidad de datos
          CASE 
            WHEN origin IS NULL OR destination IS NULL THEN FALSE
            WHEN departure_date IS NULL THEN FALSE
            WHEN num_offers IS NULL THEN FALSE
            ELSE TRUE
          END AS is_valid_record,
          
          CASE 
            WHEN num_offers = 0 THEN TRUE
            ELSE FALSE
          END AS has_no_offers,
          
          -- Métricas calculadas
          DATE_DIFF(departure_date, DATE(ingestion_timestamp), DAY) AS days_until_departure,
          
          CASE 
            WHEN DATE_DIFF(departure_date, DATE(ingestion_timestamp), DAY) <= 7 THEN 'Last Minute'
            WHEN DATE_DIFF(departure_date, DATE(ingestion_timestamp), DAY) <= 30 THEN 'Short Term'
            WHEN DATE_DIFF(departure_date, DATE(ingestion_timestamp), DAY) <= 90 THEN 'Medium Term'
            ELSE 'Long Term'
          END AS booking_window,
          
          -- Día de la semana de salida
          FORMAT_DATE('%A', departure_date) AS departure_day_of_week,
          EXTRACT(DAYOFWEEK FROM departure_date) AS departure_day_number,
          
          -- Mes y año de salida
          FORMAT_DATE('%Y-%m', departure_date) AS departure_year_month,
          EXTRACT(MONTH FROM departure_date) AS departure_month,
          EXTRACT(YEAR FROM departure_date) AS departure_year,
          
          -- Identificar fines de semana
          CASE 
            WHEN EXTRACT(DAYOFWEEK FROM departure_date) IN (1, 7) THEN TRUE
            ELSE FALSE
          END AS is_weekend_departure,
          
          -- Ruta concatenada
          CONCAT(UPPER(TRIM(COALESCE(origin, 'UNKNOWN'))), '->', 
                 UPPER(TRIM(COALESCE(destination, 'UNKNOWN')))) AS route,
          
          -- JSON fields
          search_params,
          data_payload,
          
          -- ID único
          TO_HEX(MD5(CONCAT(
            CAST(ingestion_timestamp AS STRING),
            COALESCE(origin, ''),
            COALESCE(destination, ''),
            CAST(departure_date AS STRING)
          ))) AS search_id
          
        FROM `${var.project_id}.flights_data.raw_flight_offers`
      )
      
      SELECT 
        *,
        CURRENT_TIMESTAMP() AS processed_at,
        'silver_layer' AS data_layer,
        CAST(
          (CASE WHEN is_valid_record THEN 60 ELSE 0 END) +
          (CASE WHEN NOT has_no_offers THEN 20 ELSE 0 END) +
          (CASE WHEN days_until_departure >= 0 THEN 20 ELSE 0 END)
        AS INT64) AS quality_score
      
      FROM cleaned_data
      
      WHERE is_valid_record = TRUE
        AND departure_date >= CURRENT_DATE()
      
      ORDER BY ingestion_timestamp_utc DESC
    SQL
    
    use_legacy_sql = false
  }
  
  labels = {
    layer = "silver"
    type  = "view"
  }
}