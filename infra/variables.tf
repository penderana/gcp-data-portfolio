variable "project_id" {
  description = "El ID del proyecto de Google Cloud"
  type        = string
}

variable "region" {
  description = "Región de GCP"
  type        = string
  default     = "europe-west1"
}

variable "zone" {
  description = "Zona de GCP"
  type        = string
  default     = "europe-west1-a"
}

variable "amadeus_client_id" {
  description = "Client ID de la API de Amadeus"
  type        = string
  sensitive   = true # Esto evita que salga en los logs de la consola
}

variable "amadeus_client_secret" {
  description = "Client Secret de la API de Amadeus"
  type        = string
  sensitive   = true
}