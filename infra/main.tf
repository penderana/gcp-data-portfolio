# 0. Configuracion del bucket de state
terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 4.0"
    }
  }

  backend "gcs" {
    bucket  = "terraform-state-flights" # El nombre del bucket que acabas de crear
    prefix  = "terraform/state"
  }
  # ------------------
}
# 1. Configuración del Proveedor
provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

# 2. Red Privada (VPC) - Coste 0
# Esto crea tu propio espacio de red aislado
resource "google_compute_network" "gcp-data-portfolio-cll-vpc-network" {
  name                    = "gcp-data-portfolio-cll-network"
  auto_create_subnetworks = true
}

# 3. Regla de Firewall para SSH - Coste 0
# Solo permite que alguien (tú) intente entrar por el puerto 22
resource "google_compute_firewall" "allow_ssh" {
  name    = "allow-ssh"
  network = google_compute_network.gcp-data-portfolio-cll-vpc-network.name

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = ["0.0.0.0/0"]
}

/* # 4. Máquina Virtual N2 - COMENTADA (PARA NO GENERAR COSTES)
# Solo la activaremos cuando necesitemos desplegar algo real

resource "google_compute_instance" "vm_instance" {
  name         = "flights-server" --CAMBIAR NAME
  machine_type = "n2-standard-2" 
  zone         = "europe-southwest1-a"

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2204-lts"
      size  = 20
    }
  }

  network_interface {
    network = google_compute_network.vpc_network.name
    access_config {
      # Asigna una IP pública
    }
  }
}
*/

# 5. Importacion de modulos para la creacion de tablas y vistas en GCP 
module "bigquery" {
  source = "./modules/bigquery"
}

# 6. Importacion de modulos para la creacion de la conexion terraform
module "flight_ingestion" {
  source = "./modules/flight_ingestion"

  project_id            = var.project_id
  amadeus_client_id     = var.amadeus_client_id
  amadeus_client_secret = var.amadeus_client_secret
}