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

variable "hubs" {
  description = "hub name -> { partitions, retention_days }"
  type = map(object({
    partitions     = number
    retention_days = number
  }))
}

variable "consumer_groups" {
  description = "consumer group name -> hub name"
  type        = map(string)
  default     = {}
}

variable "receiver_principal_ids" {
  type    = map(string)
  default = {}
}

variable "public_network_access_enabled" {
  description = "true (default) keeps the cheap public demo; false with private_endpoint locks the namespace to the VNet."
  type        = bool
  default     = true
}

variable "private_endpoint" {
  description = "null = no private endpoint; otherwise the subnet and the privatelink.servicebus.windows.net zone id."
  type = object({
    subnet_id   = string
    dns_zone_id = string
  })
  default = null
}
