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

variable "identity_name" {
  type = string
}

variable "log_analytics_name" {
  type = string
}

variable "app_insights_name" {
  type = string
}

variable "key_vault_name" {
  type = string
}

variable "tenant_id" {
  type = string
}

variable "daily_quota_gb" {
  type    = number
  default = 1
}

variable "key_vault_purge_protection" {
  type    = bool
  default = false
}
