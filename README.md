# ☁️ Google Cloud Data Engineering Portfolio

Este repositorio contiene una colección de pipelines de datos **End-to-End** implementados en Google Cloud Platform (GCP). El objetivo es demostrar competencias en Ingeniería de Datos moderna, desde procesamiento Batch serverless hasta Streaming en tiempo real, utilizando **Infrastructure as Code (Terraform)** y buenas prácticas de ingeniería de software.

![GCP](https://img.shields.io/badge/Google_Cloud-4285F4?style=for-the-badge&logo=google-cloud&logoColor=white)
![Terraform](https://img.shields.io/badge/Terraform-7B42BC?style=for-the-badge&logo=terraform&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Linux](https://img.shields.io/badge/Linux-FCC624?style=for-the-badge&logo=linux&logoColor=black)

---

## 📂 Estructura del Repositorio

El proyecto sigue una estructura modular separando la infraestructura del código fuente de las aplicaciones.

```bash
├── infra/                  # (Terraform)
│   ├── main.tf             # Definición de recursos 
│   └── variables.tf
├── src/                    # Código Fuente de los Pipelines
│   ├── flight-function/  # Proyecto 1
│   └── fraude/    # Proyecto 2
└── README.md


