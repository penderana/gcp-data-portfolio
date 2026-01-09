# Habilitar API de Pub/Sub
resource "google_project_service" "pubsub" {
  service = "pubsub.googleapis.com"
  disable_on_destroy = false
}

# 1. El Tópico (El canal de radio)
resource "google_pubsub_topic" "transactions_topic" {
  name = "transactions-topic"
}

# 2. La Suscripción (La grabadora)
# Necesaria para que Spark pueda "leer" lo que se ha dicho.
resource "google_pubsub_subscription" "transactions_sub" {
  name  = "transactions-sub"
  topic = google_pubsub_topic.transactions_topic.name

  # Retener mensajes 1 día por si acaso (útil para debug)
  message_retention_duration = "86400s" 
}