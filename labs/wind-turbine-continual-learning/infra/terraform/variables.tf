variable "workload" {
  description = "Workload token used in CAF names (the lab prefix)."
  type        = string
  default     = "wtg"
}

variable "environment" {
  description = "dev | test | prod"
  type        = string
}

variable "location" {
  type    = string
  default = "eastus2"
}

variable "instance" {
  type    = string
  default = "001"
}

variable "name_suffix" {
  description = "Optional suffix for globally unique names (set when forking)."
  type        = string
  default     = ""
}

variable "owner" {
  type    = string
  default = "jagadish.meduri"
}

variable "project" {
  type    = string
  default = "azure-agent-labs"
}

variable "cost_center" {
  type    = string
  default = "portfolio"
}

variable "extra_tags" {
  type    = map(string)
  default = {}
}

variable "cost_profile" {
  description = "cost-min = 1 GB/day log cap + minimum model capacity; standard = no cap, more capacity."
  type        = string
  default     = "cost-min"
  validation {
    condition     = contains(["cost-min", "standard"], var.cost_profile)
    error_message = "cost_profile must be cost-min or standard."
  }
}

variable "data_zone" {
  description = "Data zone for the DataZoneStandard deployment (processing stays in-zone)."
  type        = string
  default     = "us"
  validation {
    condition     = contains(["us", "eu"], var.data_zone)
    error_message = "data_zone must be us or eu."
  }
}

variable "diagnosis_model" {
  type    = string
  default = "gpt-5-mini"
}

variable "model_version" {
  type    = string
  default = "2025-08-07"
}

variable "key_vault_purge_protection" {
  type    = bool
  default = false
}
