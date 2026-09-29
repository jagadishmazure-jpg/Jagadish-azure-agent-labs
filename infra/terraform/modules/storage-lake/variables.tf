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

variable "replication_type" {
  type    = string
  default = "LRS"
}

variable "blob_contributor_principal_ids" {
  type    = map(string)
  default = {}
}
