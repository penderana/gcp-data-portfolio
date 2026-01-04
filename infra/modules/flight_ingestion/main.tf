variable "project_id" {}
variable "location" { default = "europe-southwest1" }
variable "amadeus_client_id" {}
variable "amadeus_client_secret" {}

# --------------------------------------------------------------------------------
# 1. ALMACENAMIENTO DE CÓDIGO (Con limpieza automática)
# --------------------------------------------------------------------------------
resource "google_storage_bucket" "function_bucket" {
  name                        = "flights-func-source-${var.project_id}"
  location                    = var.location
  uniform_bucket_level_access = true

  # COST OPTIMIZATION: Borrar zips antiguos automáticamente tras 7 días
  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type = "Delete"
    }
  }
}

# --------------------------------------------------------------------------------
# 2. EMPAQUETADO (ZIP)
# --------------------------------------------------------------------------------
data "archive_file" "function_zip" {
  type        = "zip"
  # Ruta relativa: salimos de modules/flight_ingestion/ y vamos a src/flight-function
  source_dir  = "${path.module}/../../../src/flight-function/"
  output_path = "${path.module}/function.zip"
}

resource "google_storage_bucket_object" "function_zip_object" {
  # Usamos el MD5 en el nombre para forzar el despliegue si el código cambia
  name   = "source-${data.archive_file.function_zip.output_md5}.zip"
  bucket = google_storage_bucket.function_bucket.name
  source = data.archive_file.function_zip.output_path
}

# --------------------------------------------------------------------------------
# 3. IDENTIDAD Y SEGURIDAD (Least Privilege)
# --------------------------------------------------------------------------------
locals {
  # Roles necesarios para la Cloud Function
  cloud_function_roles = [
    "roles/bigquery.dataEditor",
    "roles/bigquery.jobUser",
    "roles/cloudfunctions.invoker",
  ]
}

resource "google_service_account" "function_sa" {
  account_id   = "flight-tracker-sa"
  display_name = "Service Account para Flight Tracker"
  project = var.project_id
}

# Permiso: Escribir en BigQuery
resource "google_project_iam_member" "function_sa_roles" {
  for_each = toset(local.cloud_function_roles)
  
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.function_sa.email}"
}

# --------------------------------------------------------------------------------
# 4. GESTIÓN DE SECRETOS (Secret Manager)
# --------------------------------------------------------------------------------

# --- Secreto A: Client ID ---
resource "google_secret_manager_secret" "amadeus_id" {
  secret_id = "amadeus_client_id"
  replication {
    auto {}
  }
}
resource "google_secret_manager_secret_version" "amadeus_id_val" {
  secret = google_secret_manager_secret.amadeus_id.id
  secret_data = var.amadeus_client_id
}

# --- Secreto B: Client Secret ---
resource "google_secret_manager_secret" "amadeus_secret" {
  secret_id = "amadeus_client_secret"
  replication {
    auto {}
  }
}
resource "google_secret_manager_secret_version" "amadeus_secret_val" {
  secret = google_secret_manager_secret.amadeus_secret.id
  secret_data = var.amadeus_client_secret
}

# Permiso: La SA necesita acceso para leer los secretos
resource "google_secret_manager_secret_iam_member" "secret_access_id" {
  secret_id = google_secret_manager_secret.amadeus_id.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.function_sa.email}"
}
resource "google_secret_manager_secret_iam_member" "secret_access_key" {
  secret_id = google_secret_manager_secret.amadeus_secret.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.function_sa.email}"
}

# --------------------------------------------------------------------------------
# 5. CLOUD FUNCTION (Gen 2)
# --------------------------------------------------------------------------------
resource "google_cloudfunctions2_function" "flight_function" {
  name        = "flight-tracker-function"
  location    = var.location
  description = "Ingesta de precios de vuelos de Amadeus a BigQuery"

  build_config {
    runtime     = "python310"
    entry_point = "ingest_flight_data" # Debe coincidir con la función en main.py
    source {
      storage_source {
        bucket = google_storage_bucket.function_bucket.name
        object = google_storage_bucket_object.function_zip_object.name
      }
    }
  }

  service_config {
    max_instance_count = 1
    available_memory   = "256M"
    timeout_seconds    = 60
    service_account_email = google_service_account.function_sa.email
    
    # Variables de entorno normales
    environment_variables = {
      GCP_PROJECT_ID = var.project_id
    }

    # Inyección de secretos como variables de entorno
    secret_environment_variables {
      key        = "AMADEUS_CLIENT_ID"
      project_id = var.project_id
      secret     = google_secret_manager_secret.amadeus_id.secret_id
      version    = "latest"
    }
    secret_environment_variables {
      key        = "AMADEUS_CLIENT_SECRET"
      project_id = var.project_id
      secret     = google_secret_manager_secret.amadeus_secret.secret_id
      version    = "latest"
    }
  }
}

# --------------------------------------------------------------------------------
# 6. AUTOMATIZACIÓN (Cloud Scheduler)
# --------------------------------------------------------------------------------
resource "google_cloud_scheduler_job" "daily_trigger" {
  name        = "trigger-flight-tracker"
  description = "Dispara la Cloud Function de vuelos diariamente a las 9 AM"
  schedule    = "0 9 * * *" # Sintaxis Cron: Minuto 0, Hora 9, Todos los días
  time_zone   = "Europe/Madrid"
  region      = var.location

  http_target {
    http_method = "POST"
    uri         = google_cloudfunctions2_function.flight_function.service_config[0].uri
    
    # Autenticación OIDC para invocar la función de forma segura
    oidc_token {
      service_account_email = google_service_account.function_sa.email
    }
  }
}

# Permiso: El Scheduler (usando la SA) necesita invocar Cloud Run
resource "google_cloud_run_service_iam_member" "invoker" {
  location = google_cloudfunctions2_function.flight_function.location
  service  = google_cloudfunctions2_function.flight_function.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.function_sa.email}"
}