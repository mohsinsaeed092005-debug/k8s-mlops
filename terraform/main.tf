resource "null_resource" "minikube" {
  triggers = { name = var.cluster_name }
  provisioner "local-exec" {
    command = "minikube start -p ${var.cluster_name} --nodes ${var.nodes} --cpus ${var.cpus} --memory ${var.memory} --driver=docker && minikube addons enable ingress -p ${var.cluster_name}"
  }
  provisioner "local-exec" {
    when    = destroy
    command = "minikube delete -p ${self.triggers.name}"
  }
}

resource "kubernetes_namespace" "mlops" {
  metadata { name = "mlops" }
  depends_on = [null_resource.minikube]
}