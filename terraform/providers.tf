terraform {
  required_providers {
    null       = { source = "hashicorp/null" }
    kubernetes = { source = "hashicorp/kubernetes", version = "~> 2.30" }
  }
}
provider "kubernetes" {
  config_path    = "~/.kube/config"
  config_context = var.cluster_name
}