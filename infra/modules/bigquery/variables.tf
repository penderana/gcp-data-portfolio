variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "location" {
  description = "Location para BigQuery datasets"
  type        = string
  default     = "EU"
}