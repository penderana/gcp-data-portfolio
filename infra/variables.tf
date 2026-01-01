variable "project_id" {
  description = "El ID del proyecto de Google Cloud"
  type        = string
}

variable "region" {
  description = "Región de GCP"
  type        = string
  default     = "europe-southwest1"
}

variable "zone" {
  description = "Zona de GCP"
  type        = string
  default     = "europe-southwest1-a"
}