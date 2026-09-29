variable "resource_group_name" {
  type = string
}

variable "location" {
  type = string
}

variable "tags" {
  type    = map(string)
  default = {}
}

variable "name" {
  type = string
}

variable "identity_id" {
  type = string
}

variable "identity_principal_id" {
  type = string
}

variable "deployment_name" {
  type = string
}

variable "model_name" {
  type    = string
  default = "gpt-5-mini"
}

variable "model_version" {
  type    = string
  default = "2025-08-07"
}

variable "deployment_sku" {
  type    = string
  default = "DataZoneStandard"
}

variable "capacity" {
  type    = number
  default = 10
}
