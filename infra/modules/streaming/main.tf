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

# --------------------------------------------------------------------------------
# GENERADOR DE DATOS (VM - COMPUTE ENGINE)
# --------------------------------------------------------------------------------

# 1. Crear una identidad para la Máquina Virtual
resource "google_service_account" "fraud_vm_sa" {
  account_id   = "fraud-vm-sa"
  display_name = "Fraud Generator VM Identity"
}

# 2. Dar permiso a esa identidad para escribir en Pub/Sub
resource "google_pubsub_topic_iam_member" "vm_publisher_binding" {
  topic  = google_pubsub_topic.transactions_topic.name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${google_service_account.fraud_vm_sa.email}"
}

# 3. La Máquina Virtual
resource "google_compute_instance" "fraud_generator_vm" {
  name         = "fraud-generator-vm"
  machine_type = "e2-micro"           # Capa gratuita elegible
  zone         = "us-central1-a"      # Capa gratuita elegible

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-11"
      size  = 10 # GB
    }
  }

  network_interface {
    network = "default"
    access_config {
      # Esto asigna la IP pública 
    }
  }

  # Asignamos la identidad que creamos arriba
  service_account {
    email  = google_service_account.fraud_vm_sa.email
    scopes = ["cloud-platform"]
  }

  # 4. INSTALACIÓN AUTOMÁTICA DE DEPENDENCIAS
  # Esto se ejecuta cuando la máquina nace.
  metadata_startup_script = <<-EOF
    #! /bin/bash
    echo "Iniciando instalación de dependencias..."
    apt-get update
    apt-get install -y python3-pip git
    pip3 install --upgrade google-cloud-pubsub faker
    
    # Crear carpeta para el usuario
    mkdir -p /home/generator_user
    chmod 777 /home/generator_user
    echo "Instalación completada."
  EOF
  
  # Permitir parar/borrar la VM desde Terraform sin errores
  allow_stopping_for_update = true
}