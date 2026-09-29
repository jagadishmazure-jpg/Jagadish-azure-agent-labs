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
