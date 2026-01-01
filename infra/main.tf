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
  name         = "vaicon-server"
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